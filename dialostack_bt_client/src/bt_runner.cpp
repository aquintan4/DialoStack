// Generic runner: loads a BehaviorTree.CPP XML tree, puts an rclcpp::Node on the
// blackboard (the DialoStack nodes need it), and ticks until the tree finishes.
//
//   ros2 run dialostack_bt_client bt_runner --ros-args -p bt_xml:=/path/tree.xml
#include <memory>
#include <string>

#include "behaviortree_cpp/bt_factory.h"
#include "rclcpp/rclcpp.hpp"

#include "dialostack_bt_client/execute_dialog.hpp"

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("dialostack_bt_runner");

  node->declare_parameter<std::string>("bt_xml", "");
  node->declare_parameter<double>("tick_rate", 10.0);
  const std::string bt_xml = node->get_parameter("bt_xml").as_string();
  const double tick_rate = node->get_parameter("tick_rate").as_double();

  if (bt_xml.empty()) {
    RCLCPP_FATAL(node->get_logger(), "Set the 'bt_xml' parameter to a tree file.");
    rclcpp::shutdown();
    return 1;
  }

  BT::BehaviorTreeFactory factory;
  factory.registerNodeType<dialostack_bt_client::ExecuteDialog>("ExecuteDialog");

  auto blackboard = BT::Blackboard::create();
  blackboard->set<rclcpp::Node::SharedPtr>("node", node);

  BT::Tree tree;
  try {
    tree = factory.createTreeFromFile(bt_xml, blackboard);
  } catch (const std::exception & e) {
    RCLCPP_FATAL(node->get_logger(), "Could not load tree '%s': %s", bt_xml.c_str(), e.what());
    rclcpp::shutdown();
    return 1;
  }

  RCLCPP_INFO(node->get_logger(), "Running tree: %s", bt_xml.c_str());

  rclcpp::Rate rate(tick_rate > 0.0 ? tick_rate : 10.0);
  BT::NodeStatus status = BT::NodeStatus::RUNNING;
  while (rclcpp::ok() && status == BT::NodeStatus::RUNNING) {
    status = tree.tickOnce();
    rclcpp::spin_some(node);
    rate.sleep();
  }

  RCLCPP_INFO(
    node->get_logger(), "Tree finished: %s",
    status == BT::NodeStatus::SUCCESS ? "SUCCESS" : "FAILURE");

  rclcpp::shutdown();
  return status == BT::NodeStatus::SUCCESS ? 0 : 1;
}
