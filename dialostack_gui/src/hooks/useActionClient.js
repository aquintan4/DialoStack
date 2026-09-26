import { useCallback, useEffect, useRef, useState } from 'react'
import { useROS } from '../contexts/ROSContext'
import { useTopic } from './useTopic'
import { uuidBytes } from '../lib/ros'

let goalCounter = 0

/**
 * ROS 2 action client over the native rosbridge protocol.
 *
 * roslibjs only ships an ActionClient for ROS 1, so we send directly:
 *   { op: "send_action_goal", action, action_type, args }
 *
 * rosbridge replies with { op: "action_result", ... }, an op that roslibjs
 * silently ignores - we intercept it with a listener on the WebSocket.
 * Feedback arrives on the topic `<action>/_action/feedback`.
 */
export function useActionClient(serverName, actionName) {
  const { ros, status } = useROS()
  const [goalStatus, setGoalStatus] = useState('idle')
  const [feedback, setFeedback] = useState(null)
  const [result, setResult] = useState(null)
  const activeRef = useRef(false)
  const goalIdRef = useRef(null)
  const cancelRequestedRef = useRef(false)
  const cleanupListenerRef = useRef(null)

  useTopic(
    `${serverName}/_action/feedback`,
    `${actionName}_FeedbackMessage`,
    (msg) => {
      if (activeRef.current) setFeedback(msg.feedback ?? msg)
    }
  )

  const resetActive = useCallback((nextStatus) => {
    cleanupListenerRef.current?.()
    cleanupListenerRef.current = null
    activeRef.current = false
    goalIdRef.current = null
    if (nextStatus) setGoalStatus(nextStatus)
  }, [])

  // If rosbridge drops with a goal in flight, its result will never arrive
  // (the listener lived on the dead socket): go back to 'idle' so the UI is
  // not stuck in the active state.
  useEffect(() => {
    if (status === 'disconnected' && activeRef.current) resetActive('idle')
  }, [status, resetActive])

  useEffect(() => () => cleanupListenerRef.current?.(), [])

  const sendGoal = useCallback((goalMessage) => {
    if (!ros.current || (status !== 'connected' && status !== 'waiting')) return

    cleanupListenerRef.current?.()

    const id = `send_action_goal:${serverName}:${++goalCounter}`
    goalIdRef.current = id
    activeRef.current = true
    cancelRequestedRef.current = false
    setGoalStatus('active')
    setFeedback(null)
    setResult(null)

    const socket = ros.current.socket
    function onRawMessage(event) {
      let msg
      try {
        msg = JSON.parse(typeof event.data === 'string' ? event.data : event)
      } catch {
        return
      }
      if (msg.op !== 'action_result') return
      if (msg.id !== id && msg.action !== serverName) return

      socket.removeEventListener('message', onRawMessage)
      cleanupListenerRef.current = null

      if (!activeRef.current) return
      activeRef.current = false
      goalIdRef.current = null

      setResult(msg.values ?? {})
      setGoalStatus(msg.result ? 'succeeded' : cancelRequestedRef.current ? 'cancelled' : 'failed')
    }

    socket.addEventListener('message', onRawMessage)
    cleanupListenerRef.current = () => socket.removeEventListener('message', onRawMessage)

    ros.current.callOnConnection({
      op: 'send_action_goal',
      id,
      action: serverName,
      action_type: actionName,
      args: goalMessage,
      feedback: false,
    })
  }, [ros, status, serverName, actionName])

  // Neither cancel resets the local state: the goal stays 'active' until the
  // server confirms (action_result / status topic), so the UI can show a
  // "stopping" state instead of pretending the task already ended.
  const cancelGoal = useCallback(() => {
    if (!ros.current) return
    const id = goalIdRef.current
    cancelRequestedRef.current = true
    if (id) {
      ros.current.callOnConnection({
        op: 'cancel_action_goal',
        id,
        action: serverName,
      })
    }
  }, [ros, serverName])

  /**
   * Cancel a goal by its ROS 2 UUID via the action's cancel_goal service.
   * Unlike cancelGoal (which needs the client-side request id from this very
   * mount), this works for any goal whose UUID we know - so a GUI-launched task
   * stays cancellable after a tab switch. `goalIdStr` is the stringified uuid
   * uuid as the timeline stores it (JSON.stringify(msg.goal_id.uuid)); see
   * uuidBytes in lib/ros.js for the accepted encodings.
   */
  const cancelByUuid = useCallback((goalIdStr) => {
    if (!ros.current || !goalIdStr) return
    const uuid = uuidBytes(goalIdStr)
    if (!uuid) {
      console.warn('[DialoStack] cannot cancel: unrecognised goal id', goalIdStr)
      return
    }
    cancelRequestedRef.current = true
    ros.current.callOnConnection({
      op: 'call_service',
      service: `${serverName}/_action/cancel_goal`,
      type: 'action_msgs/srv/CancelGoal',
      args: { goal_info: { goal_id: { uuid }, stamp: { sec: 0, nanosec: 0 } } },
    })
  }, [ros, serverName])

  return { sendGoal, cancelGoal, cancelByUuid, goalStatus, feedback, result }
}
