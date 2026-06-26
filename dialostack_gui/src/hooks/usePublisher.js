import { useCallback, useRef } from 'react'
import ROSLIB from 'roslib'
import { useROS } from '../contexts/ROSContext'

/**
 * Lazy publisher for a ROS topic.
 *
 * Important: do NOT advertise on mount nor unadvertise on unmount.
 * Advertising/unadvertising a topic this same client is subscribed to makes
 * rosbridge stop delivering its messages (it broke the GUI subscription to
 * /transcription). The first publish() auto-advertises and rosbridge cleans
 * everything up on disconnect.
 */
export function usePublisher(name, messageType) {
  const { ros } = useROS()
  const topicRef = useRef(null)
  const rosInstanceRef = useRef(null)

  return useCallback((msg) => {
    if (!ros.current) return
    if (!topicRef.current || rosInstanceRef.current !== ros.current) {
      rosInstanceRef.current = ros.current
      topicRef.current = new ROSLIB.Topic({ ros: ros.current, name, messageType })
    }
    topicRef.current.publish(new ROSLIB.Message(msg))
  }, [ros, name, messageType])
}
