#ifndef DIALOSTACK_BT_CLIENT__EXECUTE_DIALOG_HPP_
#define DIALOSTACK_BT_CLIENT__EXECUTE_DIALOG_HPP_

#include <memory>
#include <string>

#include "behaviortree_cpp/action_node.h"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "ros2_dialog_interfaces/action/dialog_task.hpp"

namespace dialostack_bt_client
{

// BehaviorTree.CPP leaf node that runs one DialoStack dialogue task through the
// /dialog/execute_task action. It is a StatefulActionNode: RUNNING while the
// dialogue is in progress, then SUCCESS or FAILURE with the result on the ports.
// The tree's blackboard must hold an rclcpp::Node under the key "node".
class ExecuteDialog : public BT::StatefulActionNode
{
public:
  using DialogTask = ros2_dialog_interfaces::action::DialogTask;
  using GoalHandleDialogTask = rclcpp_action::ClientGoalHandle<DialogTask>;

  ExecuteDialog(const std::string & name, const BT::NodeConfig & conf);
  ExecuteDialog() = delete;
  ~ExecuteDialog();

  BT::NodeStatus onStart() override;
  BT::NodeStatus onRunning() override;
  void onHalted() override;

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>(
        "task_description", "Natural-language description of the dialogue task"),
      BT::InputPort<std::string>(
        "frame_schema_json", "", "Optional JSON slot schema (bypasses LLM frame generation)"),
      BT::InputPort<std::string>(
        "initial_frame_json", "", "Optional JSON pre-filling slot values (resume / prior context)"),
      BT::InputPort<std::string>(
        "dialog_mode", "", "slot_filling | explanation | quiz | empty for auto-detect"),
      BT::InputPort<std::string>(
        "domain", "", "Domain hint injected into the prompts (e.g. 'restaurant', 'hospital')"),
      BT::InputPort<bool>(
        "skip_intro", false, "Skip the opening greeting and go straight to the content"),
      BT::InputPort<std::string>(
        "resources_json", "", "Optional JSON array of {name, description, content} resources"),
      BT::InputPort<int>(
        "max_turns", 0, "Maximum dialogue turns (0 = unlimited)"),
      BT::InputPort<std::string>(
        "action_name", "/dialog/execute_task", "DialoStack action server name"),
      BT::InputPort<double>(
        "timeout", 300.0, "Total timeout for the dialogue, in seconds"),
      BT::OutputPort<std::string>(
        "final_frame_json", "JSON object with the filled slot values on success"),
      BT::OutputPort<std::string>(
        "failure_reason", "Human-readable reason for failure"),
      BT::OutputPort<int>(
        "total_turns", "Number of dialogue turns completed"),
    };
  }

private:
  void goal_response_callback(const GoalHandleDialogTask::SharedPtr & goal_handle);
  void feedback_callback(
    GoalHandleDialogTask::SharedPtr,
    const std::shared_ptr<const DialogTask::Feedback> feedback);
  void result_callback(const GoalHandleDialogTask::WrappedResult & result);

  rclcpp::Node::SharedPtr node_;
  rclcpp_action::Client<DialogTask>::SharedPtr action_client_;

  GoalHandleDialogTask::SharedPtr goal_handle_;
  rclcpp::Time start_time_;
  double timeout_;

  bool goal_accepted_;
  bool goal_completed_;
  bool goal_succeeded_;
  std::string final_frame_json_;
  std::string failure_reason_;
  int total_turns_;
};

}  // namespace dialostack_bt_client

#endif  // DIALOSTACK_BT_CLIENT__EXECUTE_DIALOG_HPP_
