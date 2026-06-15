/** Sidebar pill showing the live ROS connection status. */
import { useROS } from '../contexts/ROSContext'
import { ROS_STATUS } from '../lib/status'
import { StatusBadge } from './ui'

export function ConnectionBadge() {
  const { status } = useROS()
  const c = ROS_STATUS[status] ?? ROS_STATUS.disconnected
  return <StatusBadge {...c} />
}
