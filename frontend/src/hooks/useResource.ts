import { useEffect, useState } from 'react'
export function useResource<T>(
  loader: () => Promise<T>,
  retainWhileLoading = false,
): {
  data?: T
  error?: string
  loading: boolean
  retry: () => void
} {
  const [state, setState] = useState<{
    loader: typeof loader
    data?: T
    error?: string
    loading: boolean
  }>({ loader, loading: true })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    Promise.resolve()
      .then(() => (active ? loader() : undefined))
      .then((data) => {
        if (active) setState({ loader, data, loading: false })
      })
      .catch((reason: unknown) => {
        if (active)
          setState({
            loader,
            error:
              reason instanceof Error
                ? reason.message
                : 'This content could not be loaded. Please try again.',
            loading: false,
          })
      })
    return () => {
      active = false
    }
  }, [loader, attempt])
  return {
    ...(state.loader === loader
      ? state
      : { data: retainWhileLoading ? state.data : undefined, loading: true }),
    retry: () => {
      setState({ loader, loading: true })
      setAttempt((value) => value + 1)
    },
  }
}
