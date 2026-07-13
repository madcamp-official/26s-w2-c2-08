# KCLOUD VM 사양

> 확인 기준: 2026-07-10 11:55 (KST)

## 사양 요약

| 구분 | 사양 |
|---|---|
| 아키텍처 | x86_64 (32/64비트 지원) |
| CPU | Intel Xeon Processor (Cascade Lake), 40 vCPU |
| CPU 구성 | vCPU당 1코어 / 1스레드, NUMA 노드 1개 |
| 메모리 | 49 GiB (Swap 없음) |
| GPU | NVIDIA GeForce RTX 3090 1개 |
| GPU 메모리 | 24,576 MiB (24 GiB) |
| NVIDIA 드라이버 | 595.71.05 |
| CUDA | 13.2 |
| 루트 디스크 | 97 GiB (Virtio 블록 스토리지) |
| 네트워크 | Virtio, 내부 IPv4 `192.168.0.57/24` |
| 가상화 | KVM 완전 가상화 (Intel VT-x) |

## CPU 캐시

| 구분 | 전체 용량 |
|---|---:|
| L1 데이터 캐시 | 1.3 MiB |
| L1 명령어 캐시 | 1.3 MiB |
| L2 캐시 | 160 MiB |
| L3 캐시 | 640 MiB |

## 주요 가상 장치

- Virtio GPU
- Virtio 네트워크 장치
- Virtio 블록 스토리지
- Virtio 메모리 벌루닝
- Virtio 난수 생성기(RNG)

## GPU 확인 당시 상태

| 항목 | 상태 |
|---|---:|
| 사용 메모리 | 1 MiB / 24,576 MiB |
| GPU 사용률 | 0% |
| 온도 | 33°C |
| 소비 전력 | 10 W / 350 W |
| 실행 중인 GPU 프로세스 | 없음 |

## 메모리 및 스토리지

### 메모리

| 전체 | 사용 | 여유 | 사용 가능 | Swap |
|---:|---:|---:|---:|---:|
| 49 GiB | 465 MiB | 48 GiB | 48 GiB | 없음 |

### 디스크

| 용도 | 장치 | 전체 | 사용 | 여유 | 사용률 |
|---|---|---:|---:|---:|---:|
| 루트 파일 시스템 (`/`) | `/dev/vda1` | 97 GiB | 4.3 GiB | 93 GiB | 5% |
| EFI 부트 파티션 | `/dev/vda15` | 105 MiB | 6.1 MiB | 99 MiB | 6% |

## MVP 녹음 저장 운영 경계

현재 저장소는 `STORAGE_ROOT=data/uploads` directory만 준비하며 PDF·녹음 upload handler, resumable upload, playback과 외부 Object Storage 연동은 구현하지 않았다. 아래 내용은 원본 녹음 저장·playback MVP를 배포할 때 지켜야 할 목표 경계다.

- 97 GiB 루트 디스크는 OS, application, log, DB, PDF와 upload 중 temporary object가 함께 사용하는 자원이다. 장시간 수업 녹음의 최종 원장을 이 디스크 하나에 보관할 수 있다고 가정하지 않는다.
- 운영 MVP에는 녹음 final object를 위한 외부 Object Storage 또는 동등한 내구성·용량 경계가 필요하다. KCloud 루트 디스크는 개발, 제한된 staging·cache·temporary upload에만 사용하고 final 녹음의 유일한 사본으로 두지 않는다.
- SessionRecording의 storage key와 RecordingUpload의 temporary key는 논리 locator다. 실제로 단일 파일, 여러 part·fragment 또는 manifest를 사용할지는 미정이며 VM 문서가 물리 cardinality를 확정하지 않는다.
- final·temporary object 사용량, 일·주 증가율, 루트 디스크 여유, 소진 예상 시각, orphan object와 cleanup 실패를 모니터링해야 한다. quota와 warning·critical threshold는 미정이다.
- aggregate 삭제와 upload 만료·실패는 DB transaction에서 cleanup outbox를 남기고 storage consumer가 멱등 삭제한다. object가 이미 없으면 성공으로 처리하되 orphan reconciliation 주기·재시도 한도는 미정이다.
- 외부 Object Storage provider·region·암호화·network 경로, 녹음 동의·역할별 접근·보관·삭제, backup·restore RPO/RTO는 운영 배포 전에 확정해야 한다.

## HQ STT·canonical 후처리 운영 경계

RTX 3090은 사용할 수 있는 확인 자원일 뿐 HQ STT model이 이미 설치·배포됐다는 의미가 아니다. MVP 목표에서는 Recording upload가 완료된 뒤 `RECORDING_TRANSCRIPTION` Worker가 전체 녹음을 읽어 비canonical TranscriptVersion 아래 Segment·Gap을 준비하고, 검증에 성공해 RECORDING version이 `FINALIZED` 또는 `EMPTY`가 되는 transaction에서만 canonical 포인터를 교체한다. HQ `FAILED`·무결과 deadline에는 LIVE 포인터를 보존하되 이를 완료 기록의 final source로 인정할지는 미정이다.

- `RECORDING_TRANSCRIPTION`은 `SHARED`, `blocks_session_completion=true`인 후처리 Job이다. 다른 후처리와 동일하게 Worker는 15초마다 lease를 갱신하고 60초 동안 갱신되지 않으면 watchdog이 `FAILED`로 끝낸다.
- Gap의 `start_ms`, `end_ms`는 class(Session) timeline만 나타낸다. 녹음 seek offset은 Segment의 `recording_start_ms`, `recording_end_ms`에만 두며 `EMPTY` RECORDING version도 final Gap이 있으면 Gap-only timeline을 제공할 수 있다.
- HQ 처리 실패·lease timeout·5분 timeout은 현재 attempt가 staged한 Segment·Gap을 삭제하거나 rollback하고 `last_sequence=0`, RECORDING version·Job `FAILED`를 같은 transaction에 commit한다. cleanup 또는 reset 실패를 별도 운영 오류로 경보한다.
- Session 종료 때 만든 `SESSION_POSTPROCESSING` `SHARED` blocking coordinator는 Recording·HQ source가 terminal이 될 때까지 PENDING dependency wait 상태이며 Worker의 실행 후보로 claim하지 않는다. source terminal 뒤 mapping·Knowledge·Summary 상태를 정리하고 자신의 terminal 전이, downstream blocking Job과 outbox를 한 transaction에 commit한다.
- 자동 `FINAL_SUMMARY`는 latest HQ source가 RECORDING `FINALIZED`이고 Segment가 하나 이상일 때만 만든다. RECORDING `EMPTY`는 `NOT_APPLICABLE`·`NO_FINAL_TRANSCRIPT`, RECORDING `FAILED`·HQ 무결과 deadline·Recording source 없음은 `SUMMARY_SOURCE_UNAVAILABLE`다. 보존된 LIVE 포인터는 final source 인정 여부가 미정이므로 자동 Summary 입력으로 사용하지 않는다.
- HQ STT를 포함한 개별 후처리 Job 실행 상한은 5분이다. Session 전체 `PROCESSING`은 `ended_at`부터 최대 10분이다. deadline watchdog은 Session·coordinator를 잠그고 적용 가능한 누락 downstream blocking Job을 `FAILED`, `retryable=true`, `error_code=SESSION_PROCESSING_TIMEOUT`, `started_at=NULL`인 terminal 행으로 생성한다. Summary 상태·남은 Recording·Upload·source gate·기존 blocking Job·coordinator terminal을 같은 transaction에 확정한 뒤 completion을 평가한다.
- timeout 뒤 run token과 lease가 제거된 이전 Worker 결과는 저장하지 않는다. 모든 gate가 `SUCCEEDED` 또는 `FAILED`가 되면 일부 실패가 있어도 Session을 `COMPLETED`로 바꾸며, 완료 뒤 재시도는 Session을 다시 `PROCESSING`으로 전환하지 않는다.
- 외부 Object Storage의 녹음을 GPU Worker가 처리하려면 KCloud local staging이 필요할 수 있다. staging은 제한된 임시 공간이며 입력 fetch·처리가 끝나거나 실패·timeout되면 멱등 cleanup 대상으로 남긴다. 원본의 유일한 사본이나 canonical 결과 원장으로 사용하지 않는다.
- HQ STT model, GPU 동시 실행 수와 처리 SLO는 미정이다. 다만 어떤 model을 선택해도 공통 5분 Job 제한을 바꾸지 않는다.

운영에서는 최소한 다음 지표를 수집하고 대시보드·경보 기준을 후속 배포 결정에 연결한다.

| 영역 | 필수 지표 | 아직 미정인 운영값 |
|---|---|---|
| Queue | `RECORDING_TRANSCRIPTION` queue depth·oldest age·claim delay, coordinator dependency wait·source terminal 이후 claim delay | 동시 실행 수, warning·critical threshold |
| HQ STT | 실행 duration, 성공·`EMPTY`·실패·5분 timeout 수, 처리 녹음 duration, staged Segment·Gap rollback·삭제 및 `last_sequence` reset 실패 | model, 처리량·latency SLO |
| GPU | utilization, VRAM, OOM·provider timeout, model별 concurrency | GPU 격리·예약 방식, concurrency limit |
| Transcript | `FINALIZING` 체류, canonical switch duration·failure, Segment·Gap 수, `EMPTY` final Gap-only timeline 수 | 상태별 alert threshold |
| Staging disk | download bytes·duration, 현재·최고 bytes, free space, oldest file age | staging quota, warning·critical threshold |
| Cleanup | 성공·실패·재시도, orphan 수·bytes, timeout 뒤 잔여 파일 | reconciliation 주기와 재시도 한도 |
| Processing | coordinator terminal·downstream atomic create 실패, handoff invariant 위반, `SESSION_PROCESSING_TIMEOUT` 합성 Job 수, `ended_at` 기준 age, 10분 watchdog terminal 처리, 늦은 결과 폐기 | 운영 paging 기준 |

## 네트워크

| 항목 | 값 |
|---|---|
| 인터페이스 | `ens3` (`enp0s3`) |
| 상태 | UP |
| 내부 IPv4 | `192.168.0.57/24` (동적 할당) |
| MTU | 1450 |
| IPv6 | 링크 로컬 주소 사용 |

## 추가 확인이 필요한 항목

제공된 출력만으로는 다음 사양을 확인할 수 없다.

- 운영체제와 커널 버전
- 디스크의 실제 물리 매체 종류
- 네트워크 대역폭 및 공인 IP
- 외부 Object Storage의 provider·region·대역폭·egress 정책
- 녹음·PDF storage quota, capacity alert threshold와 backup·restore RPO/RTO
- HQ STT model, GPU concurrency limit와 처리 SLO
- HQ STT queue·Transcript 상태·staging disk·cleanup metric backend와 alert threshold
