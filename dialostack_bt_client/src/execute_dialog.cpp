#include "dialostack_bt_client/execute_dialog.hpp"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <functional>
#include <string_view>

namespace dialostack_bt_client
{

ExecuteDialog::ExecuteDialog(const std::string & name, const BT::NodeConfig & conf)
: BT::StatefulActionNode(name, conf),
  timeout_(300.0),
  goal_accepted_(false),
  goal_completed_(false),
  goal_succeeded_(false),
  total_turns_(0)
{
  auto node_any = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
  if (!node_any) {
    throw BT::RuntimeError("ExecuteDialog: 'node' not found in the blackboard");
  }
  node_ = node_any;

  std::string action_name;
  if (!getInput("action_name", action_name)) {
    action_name = "/dialog/execute_task";
  }

  action_client_ = rclcpp_action::create_client<DialogTask>(node_, action_name);
}

ExecuteDialog::~ExecuteDialog()
{
  if (goal_handle_ && !goal_completed_) {
    action_client_->async_cancel_goal(goal_handle_);
  }
}

BT::NodeStatus ExecuteDialog::onStart()
{
  goal_accepted_ = false;
  goal_completed_ = false;
  goal_succeeded_ = false;
  final_frame_json_ = "";
  failure_reason_ = "";
  total_turns_ = 0;
  goal_handle_.reset();

  std::string task_description;
  if (!getInput("task_description", task_description)) {
    RCLCPP_ERROR(node_->get_logger(), "ExecuteDialog: missing required input 'task_description'");
    return BT::NodeStatus::FAILURE;
  }

  if (!getInput("timeout", timeout_)) {
    timeout_ = 300.0;
  }

  start_time_ = node_->now();

  if (!action_client_->wait_for_action_server(std::chrono::seconds(5))) {
    RCLCPP_ERROR(node_->get_logger(), "ExecuteDialog: DialoStack action server not available");
    setOutput("failure_reason", std::string("DialoStack action server not available"));
    return BT::NodeStatus::FAILURE;
  }

  auto goal_msg = DialogTask::Goal();
  goal_msg.task_description = task_description;

  // BT.CPP 4.x treats any port value wrapped in '{}' as a blackboard reference,
  // even literal JSON objects like {"slots":[...]}. This falls back to the raw
  // attribute value when getInput() fails and the braces do not hold a plain key.
  auto readJsonPort = [this](const std::string & port_name) -> std::string {
      std::string value;
      if (getInput(port_name, value) && !value.empty()) {
        return value;
      }
      const auto & ports = config().input_ports;
      auto it = ports.find(port_name);
      if (it == ports.end() || it->second.empty()) {
        return {};
      }
      const std::string & raw = it->second;
      if (raw.size() > 2 && raw.front() == '{' && raw.back() == '}') {
        const auto inner = std::string_view(raw).substr(1, raw.size() - 2);
        const bool is_bb_key = std::all_of(
          inner.begin(), inner.end(), [](char c) {
            return std::isalnum(static_cast<unsigned char>(c)) || c == '_';
          });
        if (!is_bb_key) {
          return raw;          // literal JSON object, not a blackboard key
        }
      }
      return {};               // valid blackboard ref that was not found
    };

  const std::string frame_schema_json = readJsonPort("frame_schema_json");
  if (!frame_schema_json.empty()) {
    goal_msg.frame_schema_json = frame_schema_json;
  }

  const std::string initial_frame_json = readJsonPort("initial_frame_json");
  if (!initial_frame_json.empty()) {
    goal_msg.initial_frame_json = initial_frame_json;
  }

  std::string dialog_mode;
  if (getInput("dialog_mode", dialog_mode)) {
    goal_msg.dialog_mode = dialog_mode;
  }

  std::string domain;
  if (getInput("domain", domain)) {
    goal_msg.domain = domain;
  }

  bool skip_intro = false;
  getInput("skip_intro", skip_intro);
  goal_msg.skip_intro = skip_intro;

  std::string resources_json;
  if (getInput("resources_json", resources_json) && !resources_json.empty()) {
    goal_msg.resources_json = resources_json;
  }

  int max_turns = 0;
  if (getInput("max_turns", max_turns)) {
    goal_msg.max_turns = max_turns;
  }

  RCLCPP_INFO(
    node_->get_logger(),
    "ExecuteDialog: starting dialogue [mode='%s', domain='%s'] - '%s'",
    goal_msg.dialog_mode.c_str(),
    goal_msg.domain.c_str(),
    task_description.substr(0, 60).c_str());

  auto send_goal_options = rclcpp_action::Client<DialogTask>::SendGoalOptions();
  send_goal_options.goal_response_callback =
    std::bind(&ExecuteDialog::goal_response_callback, this, std::placeholders::_1);
  send_goal_options.feedback_callback =
    std::bind(&ExecuteDialog::feedback_callback, this, std::placeholders::_1, std::placeholders::_2);
  send_goal_options.result_callback =
    std::bind(&ExecuteDialog::result_callback, this, std::placeholders::_1);

  action_client_->async_send_goal(goal_msg, send_goal_options);

  return BT::NodeStatus::RUNNING;
}

BT::NodeStatus ExecuteDialog::onRunning()
{
  auto elapsed = (node_->now() - start_time_).seconds();
  if (elapsed > timeout_) {
    RCLCPP_ERROR(node_->get_logger(), "ExecuteDialog: timeout exceeded (%.0f s)", timeout_);
    setOutput("failure_reason", std::string("Dialogue timeout"));
    if (goal_handle_) {
      action_client_->async_cancel_goal(goal_handle_);
    }
    return BT::NodeStatus::FAILURE;
  }

  // Goal was sent but rejected before being accepted.
  if (!goal_accepted_ && goal_completed_) {
    RCLCPP_ERROR(node_->get_logger(), "ExecuteDialog: goal rejected (another dialogue running?)");
    setOutput("failure_reason", std::string("Goal rejected by DialoStack"));
    return BT::NodeStatus::FAILURE;
  }

  if (!goal_completed_) {
    return BT::NodeStatus::RUNNING;
  }

  setOutput("total_turns", total_turns_);

  if (goal_succeeded_) {
    RCLCPP_INFO(node_->get_logger(), "ExecuteDialog: completed in %d turns", total_turns_);
    setOutput("final_frame_json", final_frame_json_);
    return BT::NodeStatus::SUCCESS;
  }

  RCLCPP_ERROR(
    node_->get_logger(),
    "ExecuteDialog: failed after %d turns - %s", total_turns_, failure_reason_.c_str());
  setOutput("failure_reason", failure_reason_);
  return BT::NodeStatus::FAILURE;
}

void ExecuteDialog::onHalted()
{
  RCLCPP_WARN(node_->get_logger(), "ExecuteDialog: halted, canceling the dialogue");
  if (goal_handle_ && !goal_completed_) {
    action_client_->async_cancel_goal(goal_handle_);
  }
  goal_handle_.reset();
}

void ExecuteDialog::goal_response_callback(const GoalHandleDialogTask::SharedPtr & goal_handle)
{
  if (!goal_handle) {
    RCLCPP_ERROR(node_->get_logger(), "ExecuteDialog: goal rejected by DialoStack");
    goal_accepted_ = false;
    goal_completed_ = true;
  } else {
    RCLCPP_INFO(node_->get_logger(), "ExecuteDialog: dialogue accepted, running");
    goal_handle_ = goal_handle;
    goal_accepted_ = true;
  }
}

void ExecuteDialog::feedback_callback(
  GoalHandleDialogTask::SharedPtr,
  const std::shared_ptr<const DialogTask::Feedback> feedback)
{
  RCLCPP_INFO(
    node_->get_logger(),
    "ExecuteDialog: [turn %d | %s] \"%s\"",
    feedback->turns, feedback->state.c_str(), feedback->last_utterance.c_str());
}

void ExecuteDialog::result_callback(const GoalHandleDialogTask::WrappedResult & result)
{
  goal_completed_ = true;

  switch (result.code) {
    case rclcpp_action::ResultCode::SUCCEEDED:
      goal_succeeded_ = result.result->success;
      final_frame_json_ = result.result->final_frame_json;
      failure_reason_ = result.result->failure_reason;
      total_turns_ = result.result->total_turns;
      break;
    case rclcpp_action::ResultCode::ABORTED:
      goal_succeeded_ = false;
      failure_reason_ = result.result ? result.result->failure_reason : "Dialogue aborted";
      total_turns_ = result.result ? result.result->total_turns : 0;
      break;
    case rclcpp_action::ResultCode::CANCELED:
      goal_succeeded_ = false;
      failure_reason_ = "Dialogue canceled";
      break;
    default:
      goal_succeeded_ = false;
      failure_reason_ = "Unknown result code";
      break;
  }
}

}  // namespace dialostack_bt_client
