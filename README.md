# Chain & Context
**Beyond Code. Understanding Substance.**  
Research & Analysis by **Vanzi**

코드와 거래 기록, 계약과 제도를 연결해 **디지털자산의 실질을 해석합니다.**

기술적 권한과 법적 권리를 구분하고, 자산을 통제하는 주체와 위험·수익의 귀속을 살펴봅니다. 이 저장소에는 그 관점을 실행해 볼 수 있는 코드와 재현 기록을 축적합니다.

[홈페이지](https://www.chainandcontext.xyz/) · [실행 예제](docs/demo-walkthrough.md) · [구현 범위](docs/methodology-mapping.md) · [변경 이력](CHANGELOG.md)

## Selected work · Chain Prism

**Chain Prism · On/Off-Chain Prism (OCP)**는 코드·거래·계약·원장의 증거를 연결해 전문 판단의 근거와 한계를 기록하는 분석 프레임워크입니다.

| 문제의식 | 구현한 접근 | 확인할 결과 |
| --- | --- | --- |
| 코드상의 권한을 법적 권리·경제적 귀속으로 곧바로 간주하는 비약 | 입력·주장·구조·판단을 구분하고 근거 연결을 기록 | [방법론과 코드 대응표](docs/methodology-mapping.md) |
| 계산 결과와 전문적 결론의 혼동 | 대사 계산과 사람의 검토·승인을 분리 | [설명용 대사 데모](docs/demo-walkthrough.md) |
| 근거가 바뀌어도 과거 결론을 그대로 사용하는 문제 | 의존관계 변경 탐지·재검토·결론 스냅샷 | [구현 상세](implementation/chain-prism/README.md) |

### 현재 공개된 결과물

- **시범 구현 v0.2.1:** Python 코어·SQLite 기록·FastAPI·테스트·설명용 데모.
- **실행 검증:** 2026-11-20 업로드 전 API 포함 63개 테스트 통과. [검증 환경과 결과](implementation/chain-prism/VALIDATION-2026-11-20.md).
- **데모의 수행 범위:** 가정으로 만든 준비자산·상환의무의 산술 대사와 검토 가드레일 조회. 실제 발행자의 준비자산 검증이나 감사의견이 아닙니다.

OCP 방법론의 **v1.0**과 소프트웨어의 **v0.2.1**은 별도 판본입니다. 테스트 통과는 구현한 규칙의 동작에 관한 결과이며, 방법론 전체의 타당성·독립 재현·운영 배포 완료를 뜻하지 않습니다.

## Quick start

Python 3.12에서 검증했습니다.

```bash
git clone https://github.com/vanzi-ocp/Chain-Context.git
cd Chain-Context/implementation/chain-prism
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -v
python -m chain_prism.demo
```

Windows 활성화: `.venv\Scripts\activate`. 데모는 메모리 DB를 사용하며 외부 서비스나 지갑에 연결하지 않습니다. 출력은 **JSON 객체 두 개가 차례로 출력되는 형식**입니다. [출력 해설](docs/demo-walkthrough.md)을 함께 읽으세요.

## Expertise & approach

**공통 분석 방법 — Smart Contract & On/Off-Chain Analysis**  
스마트컨트랙트의 실행과 거래를 계약·공시·원장·입출금 내역에 대조하고, 사실·추론·가정을 구분합니다.

| 전문 영역 | 분석 관심 |
| --- | --- |
| 가상자산 인허가·규제와 토큰 권리구조 | 서비스별 규제 적용, 발행·운영주체의 의무, 청구권·상환권 |
| 크립토 AML·디지털자산 운영통제 | 개인지갑·DeFi 자금출처, 트래블룰·KYT·STR, 수탁·키·권한 통제 |
| 디지털자산 회계·경제적 실질과 토큰화 금융구조 | 인식·측정, STO/RWA 발행·조달, 가치·현금흐름·지배구조 |
| 국경 간 디지털자산 구조·국제조세 | 기능·위험·소득 귀속, PE·조세조약·이전가격·BEPS·Pillar Two·CARF·DAC8 |

위 표는 전문적 관심과 연구 방향입니다. 각 영역의 실제 수행 범위는 개별 결과물에 표시합니다.

## Repository guide

| 위치 | 내용·현재 상태 |
| --- | --- |
| [implementation/chain-prism](implementation/chain-prism/) | 실행 가능한 v0.2.1 시범 구현 |
| [docs](docs/) | 데모 해설·방법론 대응·인용 안내 |
| [cases](cases/) | 케이스스터디 보관 안내. 개별 사례팩은 아직 미수록 |
| [framework](framework/) | 방법론 자료 보관 안내 |
| [models](models/) · [sql](sql/) · [scripts](scripts/) | 모델·쿼리·스크립트 보관 안내. 개별 결과물 추가 시 갱신 |

## 기록과 공개 원칙

- 사실·추론·가정 및 자료의 기준일·관할·블록·판본을 구분합니다.
- 도구 라벨과 신뢰 점수만으로 실제 주체나 법적 권리를 확정하지 않습니다.
- 코드 구현, 설명용 실행, 실제 자료 적용, 독립 검증의 상태를 구분합니다.
- 변경은 실제 기록일과 커밋에 연결하며 과거 공개일을 추정해 채우지 않습니다.

홈페이지는 공개 작업과 해설의 입구이며, GitHub는 코드·모델·재현 기록을 관리합니다. [Notion 작업 공간](https://app.notion.com/p/418a6357b8ef8110a3fff0c1495acaa8)은 별도 접근 권한이 필요한 자료를 포함합니다.

## Citation & reuse

작성자: **Vanzi**. [인용·이용 안내](docs/citation-and-reuse.md)를 참고하세요. 이 저장소에는 현재 별도 오픈소스 라이선스가 지정되어 있지 않습니다.
