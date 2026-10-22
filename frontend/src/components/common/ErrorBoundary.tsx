import { Component } from 'react'
import type { ReactNode } from 'react'
import { ErrorState } from './ErrorState'
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <ErrorState
        title="This view is unavailable"
        message="Try reopening this page. Coordinate fields and list views can be used without the map."
        onRetry={() => this.setState({ failed: false })}
      />
    ) : (
      this.props.children
    )
  }
}
