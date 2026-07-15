# GOAL VM systemd 템플릿

이 디렉터리는 VM에 직접 설치하지 않는 템플릿이다. `/srv/goal`에 clone·`uv sync`가 끝난 뒤
관리자가 `/etc/systemd/system`으로 복사하고 `/etc/goal/goal.env`에 secret과 `AI_PROVIDER=ollama`
설정을 넣어야 한다.

`goal-worker@.service`는 `personal_ai`, `knowledge`, `clustering`, `postprocessing` instance를
지원한다. STT provider가 구현된 뒤 `recording_transcription` instance를 별도로 enable한다.
Ollama와 PostgreSQL은 이 템플릿이 설치·시작하지 않는다.
