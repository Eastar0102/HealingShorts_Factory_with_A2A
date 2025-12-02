# Google OAuth 2.0 설정 가이드

## 문제: 403 access_denied 오류

현재 "Shorts-bot" 앱이 Google 인증 절차를 완료하지 않아 접근이 차단되었습니다.

## 해결 방법

### 방법 1: 테스트 사용자 추가 (빠른 해결)

1. **Google Cloud Console 접속**
   - https://console.cloud.google.com/ 접속
   - 프로젝트 선택 (Shorts-bot)

2. **OAuth 동의 화면 설정**
   - 왼쪽 메뉴: "API 및 서비스" > "OAuth 동의 화면"
   - "사용자 유형" 선택:
     - **외부**: 일반 사용자도 사용 가능 (검증 필요)
     - **내부**: Google Workspace 내부 사용자만 (검증 불필요, 권장)

3. **테스트 사용자 추가**
   - "테스트 사용자" 섹션에서 "사용자 추가" 클릭
   - 본인 이메일 주소 추가: `idk4076@gmail.com`
   - 저장

4. **YouTube Data API v3 활성화 확인**
   - "API 및 서비스" > "사용 설정된 API"
   - "YouTube Data API v3"가 활성화되어 있는지 확인
   - 없으면 "API 라이브러리"에서 검색하여 활성화

5. **OAuth 2.0 클라이언트 ID 확인**
   - "API 및 서비스" > "사용자 인증 정보"
   - "OAuth 2.0 클라이언트 ID" 확인
   - `client_secrets.json` 파일이 올바른 클라이언트 ID를 사용하는지 확인

### 방법 2: 앱을 프로덕션으로 승인 (장기적 해결)

1. **OAuth 동의 화면 완성**
   - 앱 이름: "Shorts-bot" (또는 원하는 이름)
   - 사용자 지원 이메일: 본인 이메일
   - 앱 로고: 선택사항
   - 앱 도메인: 선택사항
   - 개발자 연락처 정보: 본인 이메일

2. **스코프 추가**
   - "범위" 섹션에서 "범위 추가 또는 삭제" 클릭
   - 다음 스코프 추가:
     - `https://www.googleapis.com/auth/youtube.upload`
     - `https://www.googleapis.com/auth/youtube` (선택사항)

3. **테스트 모드 해제**
   - "게시" 버튼 클릭
   - Google 검토 프로세스 진행 (시간 소요 가능)

### 방법 3: 내부 앱으로 설정 (가장 빠름, Google Workspace 필요)

Google Workspace를 사용하는 경우:
1. OAuth 동의 화면에서 "내부" 선택
2. 검증 없이 즉시 사용 가능
3. Google Workspace 사용자만 접근 가능

## client_secrets.json 확인

`client_secrets.json` 파일이 올바른 형식인지 확인:

```json
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uris": ["http://localhost"]
  }
}
```

또는 "웹 애플리케이션" 타입인 경우:

```json
{
  "web": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uris": []
  }
}
```

## 빠른 해결 체크리스트

- [ ] Google Cloud Console에서 프로젝트 선택
- [ ] OAuth 동의 화면에서 테스트 사용자로 본인 이메일 추가
- [ ] YouTube Data API v3 활성화 확인
- [ ] OAuth 2.0 클라이언트 ID 생성 확인
- [ ] `client_secrets.json` 파일이 올바른 형식인지 확인
- [ ] 서버 재시작 후 다시 시도

## 참고 링크

- [Google Cloud Console](https://console.cloud.google.com/)
- [OAuth 동의 화면 설정](https://console.cloud.google.com/apis/credentials/consent)
- [YouTube Data API 문서](https://developers.google.com/youtube/v3/guides/uploading_a_video)






