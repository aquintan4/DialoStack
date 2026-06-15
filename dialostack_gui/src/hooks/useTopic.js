import { useEffect, useRef } from 'react'
import ROSLIB from 'roslib'
import { useROS } from '../contexts/ROSContext'

/**
 * Subscribe to a ROS topic. The callback ref pattern ensures we always
 * call the latest version of the handler without re-subscribing on every render.
 */
export function useTopic(name, messageType, onMessage) {
  const { ros, status } = useROS()
  const callbackRef = useRef(onMessage)

  useEffect(() => {
    callbackRef.current = onMessage
  })

  useEffect(() => {
    if ((status !== 'connected' && status !== 'waiting') || !ros.current) return

    const topic = new ROSLIB.Topic({
      ros: ros.current,
      name,
      messageType,
    })

    const handler = (msg) => callbackRef.current(msg)
    topic.subscribe(handler)

    return () => topic.unsubscribe(handler)
  }, [status, name, messageType, ros])
}
