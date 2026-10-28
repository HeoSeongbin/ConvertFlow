import { Component, type ReactNode } from 'react';
export default class PreviewBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="error" role="alert">PDF 뷰어를 준비하지 못했습니다. 화면을 새로고침하거나 PDF 다운로드를 이용하세요.<button className="text-button" onClick={() => window.location.reload()}>화면 새로고침</button></div> : this.props.children;
  }
}
