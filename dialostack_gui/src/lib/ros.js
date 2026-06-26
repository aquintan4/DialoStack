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

// TTS action, used directly by the Composer's `/say <text>` test command to
// speak arbitrary text without going through the dialog engine.
export const SPEAK_ACTION = '/speak'
export const SPEAK_ACTION_TYPE = 'ros2_dialog_interfaces/action/SpeakText'

export const TOPICS = {
  transcription: { name: '/transcription', type: 'std_msgs/String' },
  robotUtterance: { name: '/robot_utterance', type: 'std_msgs/String' },
  isSpeaking: { name: '/is_speaking', type: 'std_msgs/Bool' },
  userVad: { name: '/user_vad', type: 'std_msgs/Float32' },
  userSpeaking: { name: '/user_speaking', type: 'std_msgs/Bool' },
  // Authoritative barge-in: published by the dialog manager only when it really
  // cut an utterance short. The single source of truth for the "interrupted" /
  // "barge-in" marks, replacing the old timing-based guess.
  bargeIn: { name: '/barge_in', type: 'ros2_dialog_interfaces/msg/BargeIn' },
  userEmotion: { name: '/user_emotion', type: 'std_msgs/String' },
  // LLM inference failures (provider/model/code/message). When this fires the
  // dialog has dropped to its deterministic fallback; the Monitor shows why.
  llmError: { name: '/llm/error', type: 'ros2_llm_interfaces/msg/LlmError' },
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

// ==== IMAGE TOPICS ====
// The Monitor image viewer (pages/Monitor/ImageViewer) is a debug peek: the user
// picks any image topic on the graph, so the names are not listed above. We only
// classify the message type: 'compressed' renders straight into an <img>, 'raw'
// is decoded to a canvas. Matching is suffix-based to tolerate both the 2-part
// (sensor_msgs/Image) and 3-part (sensor_msgs/msg/Image) type spellings.
export function classifyImageType(type) {
  if (!type) return null
  if (type.endsWith('CompressedImage')) return 'compressed'
  if (type.endsWith('/Image') || type === 'sensor_msgs/Image') return 'raw'
  return null
}
