# dialostack_bt_client

A [BehaviorTree.CPP](https://www.behaviortree.dev) leaf node that runs a DialoStack
dialogue from inside a behavior tree, plus a generic runner and an example.

## What it provides

- **`ExecuteDialog`**: a `StatefulActionNode` that sends a goal to the
  `/dialog/execute_task` action and reports `RUNNING` until the dialogue ends,
  then `SUCCESS` or `FAILURE`. Build it once, drop it into any tree.
- **`bt_runner`**: an executable that loads a tree XML, puts an `rclcpp::Node`
  on the blackboard (the node needs it), and ticks until the tree finishes.
- **`config/example.xml`** and **`launch/example.launch.py`**: a runnable example.

## Ports

| Port | Direction | Meaning |
|------|-----------|---------|
| `task_description` | in (required) | Natural-language task |
| `dialog_mode` | in | `slot_filling` \| `explanation` \| `quiz` \| empty for auto-detect |
| `domain` | in | Context hint for the prompts |
| `frame_schema_json` | in | Optional JSON slot schema |
| `initial_frame_json` | in | Optional pre-filled slot values (resume) |
| `resources_json` | in | Optional JSON array of resources |
| `skip_intro` | in | Skip the greeting |
| `max_turns` | in | 0 = unlimited |
| `action_name` | in | Action server (default `/dialog/execute_task`) |
| `timeout` | in | Seconds before the node gives up |
| `final_frame_json` | out | Filled slots on success |
| `failure_reason` | out | Why it failed |
| `total_turns` | out | Turns completed |

## Run the example

Start the DialoStack engine, then:

```bash
ros2 launch dialostack_bt_client example.launch.py
```

## Use it in your own tree

```xml
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <ExecuteDialog
        task_description="Take a coffee order"
        dialog_mode="slot_filling"
        final_frame_json="{order}"/>
    </Sequence>
  </BehaviorTree>
</root>
```

Any tree that uses `ExecuteDialog` must have an `rclcpp::Node` on its blackboard
under the key `node`. The `bt_runner` does this for you. The node is also built
as a plugin (`libdialostack_bt_client_plugin.so`) for `registerFromPlugin()`.
