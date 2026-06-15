/**
 * ROS names used by the GUI, centralized in a single module.
 * If a topic or action changes in the stack, only this file is touched.
 */

// rosbridge runs on the same machine that serves the GUI, but the browser may
// be on another: we derive the host from the current URL instead of hardcoding.
// The `typeof window` guard keeps the module importable outside the browser (tests).
const ROS_HOST = typeof window !== 'undefined' ? (window.location.hostname || 'localhost') : 'localhost'
export const ROSBRIDGE_URL = `ws://${ROS_HOST}:9090`

export const DIALOG_ACTION = '/dialog/execute_task'
export const DIALOG_ACTION_TYPE = 'ros2_dialog_interfaces/action/DialogTask'

export const TOPICS = {
  transcription: { name: '/transcription', type: 'std_msgs/String' },
  robotUtterance: { name: '/robot_utterance', type: 'std_msgs/String' },
  isSpeaking: { name: '/is_speaking', type: 'std_msgs/Bool' },
  userVad: { name: '/user_vad', type: 'std_msgs/Float32' },
  userSpeaking: { name: '/user_speaking', type: 'std_msgs/Bool' },
  userEmotion: { name: '/user_emotion', type: 'std_msgs/String' },
  dialogFeedback: {
    name: `${DIALOG_ACTION}/_action/feedback`,
    type: `${DIALOG_ACTION_TYPE}_FeedbackMessage`,
  },
  // Terminal state of the goals. Note: the "result" of a ROS 2 action is a
  // service (get_result), not a topic - this status is the only passive way to
  // know the task finished. 4=success, 5=canceled, 6=aborted.
  dialogStatus: {
    name: `${DIALOG_ACTION}/_action/status`,
    type: 'action_msgs/GoalStatusArray',
  },
}
