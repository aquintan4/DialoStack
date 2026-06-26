/**
 * Discover the image topics currently advertised on the ROS graph
 * (sensor_msgs/Image and sensor_msgs/CompressedImage).
 *
 * Returns the list (name + type + kind) plus a manual refresh. It also refreshes
 * automatically whenever the rosbridge connection comes up, so a topic that
 * appears after the engine starts shows without the user clicking refresh.
 */
import { useCallback, useEffect, useState } from 'react'
import { useROS } from '../contexts/ROSContext'
import { classifyImageType } from '../lib/ros'

export function useImageTopics() {
  const { ros, status } = useROS()
  const [topics, setTopics] = useState([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(() => {
    const r = ros.current
    if (!r || (status !== 'connected' && status !== 'waiting')) {
      setTopics([])
      return
    }
    setLoading(true)
    r.getTopics(
      (result) => {
        // rosbridge returns { topics: [...names], types: [...types] }
        const names = result.topics ?? []
        const types = result.types ?? []
        const found = []
        names.forEach((name, i) => {
          const kind = classifyImageType(types[i])
          if (kind) found.push({ name, type: types[i], kind })
        })
        found.sort((a, b) => a.name.localeCompare(b.name))
        setTopics(found)
        setLoading(false)
      },
      () => setLoading(false)
    )
  }, [ros, status])

  // Refresh on mount and whenever the connection status changes.
  useEffect(() => { refresh() }, [refresh])

  return { topics, loading, refresh }
}
