<p align="center"><img src="./cover.png" width="100%" /></p>

<h1 align="center">pymol-mcp</h1>
<p align="center">
  <em>헤드리스 PyMOL을 MCP 서버로 — 분자 시각화, GROMACS/LAMMPS 궤적, 클라스레이트 하이드레이트 케이지 분석을 LLM에서 직접 구동하세요.</em>
</p>
<p align="center">
  <a href="#데모">데모</a> · <a href="#빠른-시작">빠른 시작</a> · <a href="#핵심-요약">핵심 요약</a> · <a href="#기능">기능</a> · <a href="#도구-카탈로그">도구</a> · <a href="#도메인-클라스레이트-하이드레이트-과학">케이지 과학</a> · <a href="./README.md">English</a>
</p>
<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue" />
  <img src="https://img.shields.io/badge/python-3.11%2B-green" />
  <img src="https://img.shields.io/badge/PyMOL-open--source%203.x-1e40af" />
  <img src="https://img.shields.io/badge/MCP-FastMCP%203-blueviolet" />
  <img src="https://img.shields.io/badge/tests-passing-brightgreen" />
</p>

---

> [!NOTE]
> **PyMOL을 프로세스 안에서 헤드리스로** 구동하는 MCP 서버입니다 — GUI도, 소켓 플러그인도, 수동 설정도 없습니다.
> **타입이 지정된** 도구 30개 이상을 제공하고, 렌더링한 **이미지를 그대로 인라인으로 반환**해 모델이 자신이 그린 결과를 눈으로 확인할 수 있습니다.
> **GROMACS/LAMMPS** 궤적을 읽어 들이고, **수치적으로 검증된** 클라스레이트 하이드레이트 분석 도구
> (수소결합 네트워크, F3/F4 오더 파라미터)까지 갖췄습니다.

## 데모

<p align="center"><img src="./assets/pymol-mcp-demo.gif" width="100%" /></p>
<p align="center"><em>자연어로 요청 → 모델이 타입 지정 도구를 호출 → 헤드리스 PyMOL이 렌더링. (<a href="./assets/pymol-mcp-demo.mp4">고화질 MP4</a>)</em></p>

## 핵심 요약

| | |
|---|---|
| **런타임** | 임베드 **헤드리스** `pymol2` — GUI/플러그인/소켓 없음 |
| **도구** | 실제 구조화된 반환값을 갖는 **30개 이상의 타입 지정 도구** |
| **비전** | 레이트레이싱 PNG를 **인라인 반환**하여 모델이 그린 결과를 직접 확인 |
| **MD 궤적** | GROMACS `.xtc/.trr` + LAMMPS 덤프 (MDAnalysis 브리지) |
| **도메인 과학** | 케이지 인식(TRACE), 점유율, 수소결합, F3/F4 — **검증됨** |
| **견고성** | 워커 스레드 세션, **stdout 안전** 전송, pytest 스위트 |
| **안전성** | 임의 코드 실행 패스스루 **기본 꺼짐** |

## 기능

- **임베드 & 헤드리스** — 전용 워커 스레드에서 단일 PyMOL 인스턴스를 유지; 클릭할 것이 없고 CI에서도 동작.
- **모델이 *볼 수* 있음** — `render_image`가 레이트레이싱한 PNG를 MCP 이미지 콘텐츠로 반환.
- **MD 네이티브** — GROMACS `.gro`+`.xtc`를 바로 읽고, LAMMPS/NetCDF는 MDAnalysis로 좌표를 메모리에 직접 주입해 연결.
- **클라스레이트 하이드레이트 도구** — 검증된 Rust 엔진에서 이식한 수소결합 네트워크와 **F3/F4** 오더 파라미터. 모든 계산은 nm 단위로, 삼사정계 PBC까지 정확히 처리.
- **타입 지정, 안전한 도구** — 모든 인자가 스키마로 검증됨; 임의 코드 실행은 **옵트인**(`PYMOL_MCP_ALLOW_CODE_EXEC=1`).
- **프로토콜 안전** — PyMOL이 stdout으로 쏟아내는 출력을 영구 리다이렉트해 JSON-RPC 스트림을 절대 오염시키지 않음(서브프로세스 테스트로 증명).

## 빠른 시작

> [!IMPORTANT]
> PyMOL 오픈소스는 **conda** 패키지이며, 서버는 `import pymol2`가 가능한 파이썬에서 실행되어야 합니다.
> 해당 인터프리터에 설치하세요 — `uvx`/`fastmcp install`은 PyMOL이 없는 격리 환경을 만들므로 사용하지 **마세요**.

```bash
# 1. 환경 생성 (또는 pymol-open-source가 이미 있는 환경 재사용)
conda env create -f env.yml        # `pymol-mcp` 환경
conda activate pymol-mcp

# 2. 패키지 설치 (MD 브리지 + 개발 도구 포함)
pip install -e ".[md,dev]"

# 3. 검증
pytest -q
```

**stdio 기반 표준 MCP 서버**이므로 MCP를 지원하는 모든 클라이언트에서 사용할 수 있습니다
(Claude Code / Desktop, Codex CLI, Gemini CLI, Cline, Continue 등). `import pymol2`가 가능하도록
command를 **절대 경로** conda 인터프리터로 지정하세요.

대부분의 클라이언트는 `mcpServers` 블록을 사용합니다 (Claude Code / Desktop, Gemini CLI, Cline, Continue 등):

```json
{
  "mcpServers": {
    "pymol": {
      "command": "/절대/경로/conda/envs/pymol-mcp/bin/python",
      "args": ["-m", "pymol_mcp"]
    }
  }
}
```

<details>
<summary><b>Codex CLI</b> — <code>~/.codex/config.toml</code></summary>

```toml
[mcp_servers.pymol]
command = "/절대/경로/conda/envs/pymol-mcp/bin/python"
args = ["-m", "pymol_mcp"]
```
</details>

옵트인 스크립팅 도구를 켜려면 서버 항목에 `"env": {"PYMOL_MCP_ALLOW_CODE_EXEC": "1"}`을 추가하세요.

이후 에이전트에게 이렇게 요청하세요:

```
./hydrate.gro 를 로드하고, 물을 F4 오더 파라미터로 색칠한 뒤 렌더링해줘.
md.gro + traj.xtc 를 로드하고, CO2 게스트를 구로 표시한 뒤 50번째 프레임을 렌더링해줘.
이 구조에서 물의 평균 수소결합 배위수는 얼마야?
```

## 도구 카탈로그

| 그룹 | 도구 |
|-------|-------|
| **세션 / IO** | `load_structure` · `fetch_pdb` · `list_objects` · `get_object_info` · `reset_session` |
| **선택** | `select` · `get_selection_info` |
| **표현** | `show` · `hide` · `color` · `spectrum` · `set_background` |
| **뷰 / 렌더** | `orient` · `zoom` · `turn` · `render_image` → 🖼️ 인라인 PNG |
| **측정** | `measure_distance` · `measure_angle` · `measure_dihedral` · `align` · `save_file` |
| **궤적 / MD** | `load_trajectory` (GROMACS/DCD) · `load_trajectory_mda` (LAMMPS/NetCDF, MDAnalysis) |
| **클라스레이트 도메인** | `identify_cages` (TRACE) · `cage_occupancy` · `mark_cages` · `hbond_network` · `order_parameter` (F3 / F4) |
| **스크립팅 (옵트인)** | `run_pml` · `run_python` |

## 도메인: 클라스레이트 하이드레이트 과학

검증된 Rust 레퍼런스 구현에서 이식한 뒤 정답값과 대조해 재검증했습니다. 모든 분석은 **나노미터** 단위이며,
분수좌표 기반 **최소 이미지 규약**(직교·삼사정계 모두), F4용 부호 있는 `atan2` 이면각, 주기 이미지 KDTree 이웃 탐색을 사용합니다.

- **`identify_cages`** — 완전한 TRACE 케이지 인식: 링 탐색 → 기하 검증 → 제약 전파 조립 → 오일러(SEC) 검증 → 면 개수로 유형 분류(5¹², 5¹²6², 5¹²6⁴, …) 및 sI/sII/sH 구조 판정.
- **`cage_occupancy`** — 게스트 분자(CO₂/CH₄)를 케이지에 할당하고 유형별 점유율(θ_S, θ_L) 보고.
- **`mark_cages`** — 각 케이지 중심에 색상 구를 배치하여 `render_image`로 케이지 격자를 시각화.
- **`order_parameter`** — F4(비틀림), F3(3체 각도). F4 ≈ 0.7–0.95 → 하이드레이트, ≈ 0 → 액체, ≈ −0.4 → 얼음 Ih.
- **`hbond_network`** — 물 수소결합 그래프 (O–O ≤ 0.36 nm 및 도너 H–O···O 각 < 35°) + 배위 통계.

<p align="center"><img src="./assets/cages_demo.png" width="66%" /><br/><em>검출된 sII 케이지를 와이어프레임 다면체로 시각화: 5¹² 십이면체(청록)가 5¹²6⁴ 케이지(빨강)를 면 공유로 둘러싼 모습.</em></p>

> [!TIP]
> **정답값 대비 검증:** 구조 II 레퍼런스에서 `identify_cages`가 정확히 **128 × 5¹² + 64 × 5¹²6⁴** 케이지(교과서적 2:1 sII 격자)를,
> 구조 I에서 정확히 **16 × 5¹² + 48 × 5¹²6²**를 찾습니다. 첫 10개 물 분자의 F4는 레퍼런스 값 **0.926698**을 정확히 재현하고,
> F3 = 0.0028 (하이드레이트-유사 ≤ 0.04), 수소결합 네트워크는 완벽한 정사면체(평균 배위수 4.00) 골격입니다.

## 동작 원리

```
   MCP 클라이언트 (Claude · Codex · Gemini …)
          │  stdio JSON-RPC
          ▼
 ┌───────────────────────────────────────────────┐
 │  pymol-mcp  (FastMCP, pymol2가 있는 conda 환경)  │
 │   • 영구 stdout 리다이렉트 (프로토콜 안전)         │
 │   • 단일 워커 스레드가 pymol2 소유 + 구동          │
 │   • 타입 지정 @mcp.tool 함수                      │
 └───────────────────────────────────────────────┘
      │ cmd.* (헤드리스)         │ numpy / scipy (nm)
      ▼                          ▼
  PyMOL 3.x  ── ray → PNG    analysis/ (수소결합, F3/F4)
```

## 요구 사항

| 의존성 | 필수 | 용도 |
|-----------|----------|---------|
| Python 3.11+ (conda) | 예 | `import pymol2` 가능한 런타임 |
| `pymol-open-source` 3.x | 예 | 시각화 엔진 (conda) |
| `fastmcp` 3.x, `numpy`, `scipy` | 예 | MCP 서버 + 분석 |
| `MDAnalysis` | 아니오 (`md` extra) | LAMMPS / NetCDF / xtc 브리지 (GPL-2.0+) |
| `ffmpeg` | 아니오 | 동영상 내보내기 (예정) |

## 라이선스

[MIT](./LICENSE). 선택적 `md` extra는 **MDAnalysis**(GPL-2.0-or-later)를 지연 임포트하며, 코어 패키지는 MIT를 유지합니다.
