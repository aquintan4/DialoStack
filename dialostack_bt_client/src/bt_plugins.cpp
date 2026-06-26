// Registers the DialoStack BT nodes so the library can be loaded at runtime
// with BT::BehaviorTreeFactory::registerFromPlugin("libdialostack_bt_client_plugin.so").
#include "behaviortree_cpp/bt_factory.h"

#include "dialostack_bt_client/execute_dialog.hpp"

BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<dialostack_bt_client::ExecuteDialog>("ExecuteDialog");
}
