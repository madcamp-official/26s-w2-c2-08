# GOAL KCLOUD pull 배포

이 디렉터리는 VM에 직접 설치하지 않는 systemd 템플릿이다. 배포기는 2분마다 공개 GitHub
저장소의 `main` SHA를 확인하고, 그 SHA에서 실행된 `push` event의 `CI` workflow가 성공한 경우에만
새 release를 활성화한다. GitHub Ruleset이나 배포 승인은 필요하지 않다. 저장소가 private이거나
API rate limit을 높여야 할 때만 Actions·Contents read-only token을 사용한다.

## 실행 구조

```text
/opt/goal/
├── repo/                       bare Git cache
├── releases/<commit-sha>/      immutable application release
├── current -> releases/<sha>
├── previous -> releases/<sha>
├── shared/backups/             pre-migration pg_dump
└── state/                      deployed SHA, failed SHA, deploy lock
```

PDF·녹음 storage와 PostgreSQL data는 release directory 밖에 둔다. `/opt/goal/current` 교체는
원자적으로 수행하며 API와 Worker는 이 경로만 바라본다.

## 최초 설치

1. `goal`과 `goal-deploy` system user를 만든다.
2. `/opt/goal`을 만들고 `goal-deploy:goal-deploy`가 release·backup·state를 쓸 수 있게 한다.
3. `deploy/bin/goal-*`을 `/usr/local/sbin`에 root 소유, mode `0755`로 설치한다.
4. `deploy/deploy.env.example`을 `/etc/goal/deploy.env`로 복사해 root 소유 `0640`, group
   `goal-deploy`로 설정한다.
5. production application 설정을 `/etc/goal/goal.env`에 shell-compatible `KEY=value` 형식으로
   저장하고 root 소유 `0640`, group `goal-deploy`로 설정한다.
6. systemd unit을 `/etc/systemd/system`에, sudoers template을 `/etc/sudoers.d/goal-deploy`에
   설치하고 `visudo -cf`로 검사한다.
7. `systemctl daemon-reload` 뒤 API·필요 Worker·`goal-deploy.timer`를 enable한다.

Public repository에는 token file을 만들지 않아도 된다. token을 쓸 때는 채팅이나 repository에
넣지 않고 `/etc/goal/secrets/github_deploy_token`에 한 줄로 저장하며 root 소유 `0640`, group
`goal-deploy`로 제한한다.

## 배포 경계

`goal-deploy-if-needed`는 remote `main`과 배포 SHA가 다를 때 GitHub Actions API를 조회한다.
workflow file·branch·event·commit SHA를 함께 고정하고 최신 run attempt가
`completed/success`인 경우에만 `goal-deploy`를 호출한다. CI가 진행 중이거나 없으면 기다리고,
실패·취소되면 배포하지 않는다.

`goal-deploy`는 lock, SHA 재검증, frozen dependency install, frontend build, production 설정
검증, `pg_dump`, Alembic upgrade, symlink 교체, service restart와 DB health check를 순서대로
수행한다. 활성화 뒤 실패하면 코드 symlink와 process는 이전 release로 복구하지만 DB migration은
자동 downgrade하지 않는다. 자동 배포 migration은 이전 코드와 호환되는 expand/contract 형태여야
한다.

`goal.env`의 `STORAGE_ROOT`는 `/opt/goal/shared/storage` 같은 release 밖의 절대 경로여야 한다.
VM에는 build 도구 외에 `curl`, `git`, `flock`, `tar`, PostgreSQL client의 `pg_dump`가 필요하다.

기본 Worker는 `material`, `knowledge`, `clustering`, `personal_ai`, `postprocessing`, `lifecycle`다.
`recording_transcription`은 Faster-Whisper 운영 설정과 GPU 경계를 확인한 뒤 `GOAL_SERVICES`와
sudoers 양쪽에 추가한다. Ollama와 PostgreSQL 자체는 application 배포 때 재시작하지 않는다.

Faster-Whisper GPU Worker는 CUDA 12 cuBLAS와 cuDNN 9을 함께 로드한다. cuDNN은
backend 가상환경의 `nvidia-cudnn-cu12` package에서, cuBLAS는 KCloud Ollama CUDA 12
runtime에서 공급하며 `goal-worker@.service`의 `LD_LIBRARY_PATH`를 유지한다.

## 운영 확인

```bash
make deploy-check
systemctl status goal-deploy.timer
systemctl list-timers goal-deploy.timer
journalctl -u goal-deploy.service -f
sudo -u goal-deploy /usr/local/sbin/goal-deploy-if-needed
```

동일 SHA를 다시 시도하려면 실패 원인을 해결한 뒤 관리자가 `goal-deploy <sha>`를 직접 실행한다.
운영 backup 보관 기간·외부 복제·복구 RPO/RTO는 아직 미정이며 별도 확정이 필요하다.
