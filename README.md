# Token Ledger Prism
**Digital Asset Research & Analytics**  
*From Code to Economic Substance* · Research by **Vanzi**

스마트컨트랙트·온체인 증거와 오프체인 권리·의무를 연결해 디지털자산의 법률·경제적 실질을 연구합니다.

## Research domains

- **Digital Asset & Smart Contract Structures** — DeFi, stablecoins, RWA/STO, tokenomics.
- **On-Chain Analytics & Compliance** — on-chain analysis, AML/CFT, transaction monitoring.
- **Digital Asset Policy** — licensing, governance, policy analysis.
- **Valuation & Economic Substance** — valuation, accounting, taxation, CARF/DAC8.

## Research workspace

[Notion Research Hub](https://app.notion.com/p/418a6357b8ef8110a3fff0c1495acaa8)는 연구 기획·사례·출처·원고를 관리합니다. 이 저장소는 버전 관리가 필요한 분석 파일·모델·SQL·코드와 재현 안내를 축적합니다. Notion 열람에는 별도 접근 권한이 필요할 수 있습니다.

| Directory | Purpose |
| --- | --- |
| [cases](cases/) | 사례별 근거·분석·가정·재현 기록 |
| [framework](framework/) | Chain Prism 방법론과 기능 카드의 저장 위치 |
| [models](models/) | 가치평가·현금흐름·대사 모델 |
| [sql](sql/) | 온체인 데이터 조회·대사 쿼리 |
| [scripts](scripts/) | 자료 수집·변환·검증 코드 |
| [implementation/chain-prism](implementation/chain-prism/) | OCP 판단·증거·검토 기록 시범 구현 v0.2.1 |

## Chain Prism / OCP

*Substance over Code*

권한·권리·통제·귀속을 구분하고, 코드·거래·문서·장부를 연결해 판단 근거를 남기는 분석 프레임워크입니다. 연구 브랜드는 Token Ledger Prism, 작성자 필명은 Vanzi, 방법론은 Chain Prism입니다.

## Current status

[Chain Prism 시범 구현 v0.2.1](implementation/chain-prism/)을 수록했습니다. 증거·판단·작성자/검토자 분리·차이 기록·결론 스냅샷을 다루는 Python 코어와 API, 데모 및 테스트를 포함합니다. 설치·실행 방법과 구현 범위는 패키지 README를 참고하세요.

2026-11-20 업로드 전 검증에서는 API 테스트를 포함해 63개가 통과했습니다. [검증 기록](implementation/chain-prism/VALIDATION-2026-11-20.md)을 함께 보관합니다. 시범 구현은 자동 회계·조세 판단이나 운영 시스템 연동의 완료를 뜻하지 않습니다. 기존 원고·실증 사례의 수행 범위와 코드의 구현 범위는 별도로 확인합니다.

## Research principles

- 사실·추론·가정을 구분하고 출처·기준일·관할·블록·코드 버전을 기록합니다.
- 실제 사례에 추가한 가정·스트레스·대안 구조를 실제 사실과 구분합니다.
- 도구의 라벨·신뢰 점수만으로 실제 주체나 법적 권리를 확정하지 않습니다.
- 문서화, 시드, 부분 적용, 실행 검증의 상태를 구분합니다.
- 모델·코드를 추가할 때 입력 출처, 실행 방법, 예상 결과와 한계를 함께 기록합니다.
