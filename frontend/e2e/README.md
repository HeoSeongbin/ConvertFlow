# 실제 브라우저 검증

기본 실행은 루트의 `docker compose run --rm --build e2e`다. Chromium·Firefox·모바일 크기 WebKit을 고정한 공식 Linux 이미지로 실행한다. 전체 실행과 Worker 정지 중 `@queued` 검증은 `python scripts/validate_phase7.py --faults`를 사용한다.

`fixtures/cover.png`는 96×64 빨간 RGB 이미지, `pages.tiff`는 같은 크기 초록·파랑 2프레임이다. Pillow로 만든 합성 이미지이며 외부 저작물이나 개인정보는 없다. PNG를 TIFF보다 위로 옮긴 실제 PDF Canvas 중앙 픽셀로 순서를 검증한다. PDF 옵션·페이지 구조는 기존 Python smoke에서 별도로 파싱한다.

정상 Job/이벤트/Attempt API를 모킹하지 않는다. 네트워크 오류 시나리오에서만 브라우저의 download 요청을 abort하고 해제해 복귀를 검사한다. 기본 네 시나리오×세 브라우저=12개, Worker 정지 전용 한 시나리오×세 브라우저=3개다. 컨텍스트마다 새 workspace를 사용한다.

E2E 타입은 `tsconfig.e2e.json`으로 검사하고 Vitest는 e2e 디렉터리를 제외한다. 호스트 실행 시 `npm ci`, `npx playwright install`, `npm run test:e2e`를 사용할 수 있지만 공식 재현 경로는 Docker다. 실패 자료는 `.gitignore`로 제외하며 공개하지 않는다.
