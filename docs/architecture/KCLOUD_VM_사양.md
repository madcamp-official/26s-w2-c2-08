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
