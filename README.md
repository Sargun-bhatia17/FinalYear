# 🔍 AttentionLens

> **A completely local, privacy-first, adaptive desktop application that understands how you focus — and helps you focus better.**

AttentionLens runs entirely on your machine. No cloud. No subscriptions. No data ever leaves your device. It silently observes your computer activity patterns, applies multi-parameter behavioral mathematics, and uses a locally trained machine learning model to tell you — in plain language — whether you are in Deep Work, Pondering, Passive Leisure, or drifting away.

---

## 📖 Table of Contents

- [What Problem Does This Solve?](#-what-problem-does-this-solve)
- [Core Features](#-core-features)
- [Architecture Overview](#️-architecture-overview)
- [Technology Stack](#️-technology-stack)
- [Database Schema](#️-database-schema)
- [Behavioral Scoring Engine](#-behavioral-scoring-engine)
- [Loophole Resolution Protocols](#-loophole-resolution-protocols)
- [Local Machine Learning Pipeline](#-local-machine-learning-pipeline)
- [Confidence-Aware Fusion Engine](#-confidence-aware-fusion-engine)
- [Actionable Recommendation System](#-actionable-recommendation-system)
- [Implementation Roadmap](#️-implementation-roadmap)
- [Project Structure](#-project-structure)
- [Privacy Guarantee](#-privacy-guarantee)

---

## 🎯 What Problem Does This Solve?

Most productivity trackers are either too simple (just a timer) or too invasive (cloud-synced screenshots). AttentionLens fills the gap with **intelligent, local behavioral analysis**:

| Problem | How AttentionLens Solves It |
|---|---|
| "Am I actually focused or just staring at VS Code?" | Ghost Focus detection catches zero-activity idle states |
| "I'm scrolling a textbook — am I being productive?" | Multi-parameter math distinguishes reading from browsing feeds |
| "I was solving a hard problem and barely typed anything" | DSA Pondering Exception prevents false idle flags |
| "I don't trust cloud apps with my work habits" | 100% offline — SQLite + local ML, zero network calls |
| "Generic trackers don't know my apps" | Dynamic user taxonomy self-learns your personal workflow |

---

## ✨ Core Features

### 🧩 Adaptive Attention State Classification
Classifies every 60-second interval into one of four states:
- **Deep Work** — High interaction, focused in core tools, low context switching
- **Pondering** — Near-zero input in technical/academic windows (e.g., staring at a LeetCode problem)
- **Passive Leisure** — Low input, high scroll velocity in entertainment contexts
- **Idle / Away** — No interaction detected in an active window for 3+ minutes

### 📊 Multi-Parameter Behavioral Math
Scores behavior across four distinct mathematical axes — Interaction Density, Scroll Velocity, Context Switching Entropy, and Category Distance — to produce a precise Attention Risk Score.

### 🛡️ Loophole-Free Rule Engine
Four deterministic override protocols catch edge cases that pure ML would misclassify:
- The DSA Pondering Exception
- The Comic/Manga Consumer Loophole
- The Ghost Focus / Left the Desk Catch
- Rewriting History (retroactive state correction)

### 🤖 Locally Trained Personalization
A scikit-learn Random Forest model lives entirely on your disk. It retrains automatically in the background once 100 new sessions accumulate or every 7 days — becoming smarter about *your* specific workflow over time.

### 🔀 Confidence-Aware Fusion
Blends the deterministic Rule Engine and the adaptive ML model using a mathematically calculated trust weight. When data is scarce, rules dominate. As data grows, the local model takes over — but rules always maintain a 20% floor to catch major deviations.

### 💬 Actionable Contextual Alerts
When the attention risk score stays critically high for 3+ minutes, the engine emits a structured JSON alert with a diagnosed cause and a specific behavioral prompt — not just a percentage warning.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER'S LOCAL MACHINE                        │
│                                                                 │
│  ┌───────────────────────────────────┐                          │
│  │     Tauri + React  (Frontend)     │  ← Native desktop window │
│  │   Dashboard · Timeline · Alerts   │    (<20MB install, low RAM)│
│  └──────────────┬────────────────────┘                          │
│                 │  localhost WebSocket / HTTP REST               │
│                 │  (randomized high port, e.g. :8421)           │
│  ┌──────────────▼────────────────────┐                          │
│  │   Python Sidecar Process          │  ← Independent background│
│  │                                   │    worker process        │
│  │  ┌─────────────────────────────┐  │                          │
│  │  │  Layer 1: OS Window Hooks   │  │  pywin32 / AppKit        │
│  │  │  + pynput Input Listeners   │  │                          │
│  │  └────────────┬────────────────┘  │                          │
│  │               │ every 5 seconds   │                          │
│  │  ┌────────────▼────────────────┐  │                          │
│  │  │  Layer 2: SQLite Repository │  │  raw_window_events       │
│  │  │  (Repository Pattern)       │  │  behavioral_sessions     │
│  │  └────────────┬────────────────┘  │  user_taxonomy           │
│  │               │ every 60 seconds  │                          │
│  │  ┌────────────▼────────────────┐  │                          │
│  │  │  Layer 3–4: Behavior Engine │  │  I_D · S_V · E_C · C_D  │
│  │  │  + Loophole Protocols       │  │  + 4 override rules      │
│  │  └────────────┬────────────────┘  │                          │
│  │               │                   │                          │
│  │  ┌────────────▼────────────────┐  │                          │
│  │  │  Layer 5–7: Feature Eng.    │  │  f0–f4 feature vector    │
│  │  │  + Local Random Forest      │  │  scikit-learn .joblib    │
│  │  └────────────┬────────────────┘  │                          │
│  │               │                   │                          │
│  │  ┌────────────▼────────────────┐  │                          │
│  │  │  Layer 8–9: Fusion Engine   │  │  W_ml + W_rule blending  │
│  │  │  + Recommendation System    │  │  Structured alert JSON   │
│  │  └─────────────────────────────┘  │                          │
│  └───────────────────────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| **Desktop Window** | [Tauri](https://tauri.app/) | Native OS wrapper, <20MB install, minimal RAM |
| **UI Framework** | React (TypeScript) | Component-driven dashboard, hot-reload dev |
| **Core Engine** | Python (Sidecar Process) | Low-level OS hooks, ML libraries, async loops |
| **OS Window Hooks** | `pywin32` (Windows) / `AppKit` (macOS) | Native active-window querying |
| **Input Listeners** | `pynput` | Silent global mouse/keyboard delta capture |
| **Database** | SQLite (embedded) | Zero-setup, fully local, file-based |
| **DB Access Pattern** | Repository Pattern class | Future-proof: swap SQLite → PostgreSQL in one file |
| **ML Model** | `scikit-learn` Random Forest | CPU-only, <5MB `.joblib` binary, fast inference |
| **IPC** | Local WebSocket / `localhost` HTTP | Secure, no external socket, randomized port |
| **Model Serialization** | `joblib` | Seamless hot-swap retraining without app restart |

---

## 🗄️ Database Schema

Three tables form the complete data backbone of AttentionLens.

### Table 1: `raw_window_events` — Chronological Activity Log
```sql
CREATE TABLE IF NOT EXISTS raw_window_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_name        TEXT NOT NULL,      -- e.g., "chrome.exe", "Code.exe"
    window_title        TEXT NOT NULL,      -- e.g., "LeetCode – Two Sum – Chrome"
    keystroke_count     INTEGER DEFAULT 0,  -- Keys pressed in this interval
    mouse_click_count   INTEGER DEFAULT 0,  -- Clicks in this interval
    scroll_delta_y      INTEGER DEFAULT 0   -- Vertical scroll pixels moved
);
```
> Written every **5 seconds** by the background event accumulator loop.

---

### Table 2: `behavioral_sessions` — Aggregated 60-Second Windows
```sql
CREATE TABLE IF NOT EXISTS behavioral_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time          DATETIME NOT NULL,
    end_time            DATETIME NOT NULL,
    primary_process     TEXT NOT NULL,
    primary_category    TEXT NOT NULL,      -- Via Dynamic Taxonomy lookup
    scroll_velocity     REAL NOT NULL,      -- Pixels scrolled per second (S_V)
    input_density       INTEGER NOT NULL,   -- Total interactions (I_D)
    has_text_selection  BOOLEAN NOT NULL,   -- True if highlighting occurred
    calculated_state    TEXT NOT NULL,      -- "Deep Work" | "Pondering" | "Passive Leisure" | "Idle"
    attention_risk_score REAL NOT NULL      -- Fusion engine output (0.0 → 1.0)
);
```

---

### Table 3: `user_taxonomy` — Personalized App Classification
```sql
CREATE TABLE IF NOT EXISTS user_taxonomy (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    process_or_keyword   TEXT UNIQUE NOT NULL, -- e.g., "Figma", "LeetCode", "notion"
    assigned_category    TEXT NOT NULL,        -- "Core_Tool" | "Supporting_Tool" | "Leisure"
    confidence_weight    REAL DEFAULT 1.0      -- Modified via self-learning baseline
);
```

---

## 📐 Behavioral Scoring Engine

Every 60 seconds, the engine processes the last minute of raw events through four scoring parameters:

### Parameter A — Interaction Density ($I_D$)
Physical engagement frequency per interval:
$$I_D = \text{keystroke\_count} + \text{mouse\_click\_count}$$

### Parameter B — Scroll Velocity ($S_V$)
Structural canvas movement speed:
$$S_V = \frac{|\text{scroll\_delta\_y}|}{\text{interval\_duration\_seconds}}$$

### Parameter C — Context Switching Entropy ($E_C$)
Predictability of application switching over a rolling 5-minute window. Let $p_i$ = proportion of time in app category $i$:
$$E_C = -\sum (p_i \cdot \log_2(p_i))$$

| Entropy Value | Interpretation |
|---|---|
| $E_C < 0.8$ | Focused: 1–2 related apps (e.g., editor ↔ docs) |
| $0.8 \le E_C \le 1.8$ | Moderate switching — normal workflow |
| $E_C > 1.8$ | High chaos: jumping across unrelated apps |

### Parameter D — Category Distance ($C_D$)
Risk score for each app switch:

| From Category | To Category | Distance Score | Context |
|---|---|---|---|
| `Core_Tool` | `Supporting_Tool` | **0.1** | Safe auxiliary shift |
| `Core_Tool` | `Core_Tool` | **0.0** | Same workspace execution |
| `Core_Tool` | `Leisure` | **1.0** | High-risk focus disruption |

---

## 🛡️ Loophole Resolution Protocols

Four hardcoded override rules sit between the raw math and the final state label. These eliminate the most common misclassification scenarios.

---

### Protocol 1 — The DSA Pondering Exception
**Scenario:** Developer is staring at a LeetCode problem, thinking through the algorithm. Zero typing. The naive system would flag this as Idle.

**Trigger Conditions:**
- Window title contains: `leetcode`, `github`, `docs`, `coursework`, `tutorial`
- $I_D \le 2$ (near-zero typing)
- $S_V \le 5$ (minimal scrolling)

**Action:**
- Set `calculated_state = "Pondering"` ✅
- Extend focus timeout from **3 minutes → 20 minutes**
- Do NOT penalize the attention risk score

---

### Protocol 2 — The Comic / Manga Consumer Loophole
**Scenario:** User is reading manga online — physically scrolling every 60 seconds. The system could misclassify this as engaged reading.

**Trigger Conditions:**
- Window title contains: `chapter`, `manga`, `comic`, `scan`, `feed`
- $I_D$ is low
- $S_V > 40$ (rapid vertical scrolling)

**Action:**
- Set `calculated_state = "Passive Leisure"` ✅
- Immediately increase attention risk score by **+0.45**
- High scroll speed + leisure keywords overrides any pondering rule

---

### Protocol 3 — The Ghost Focus / Left the Desk Catch
**Scenario:** VS Code is the active window, but the user stepped away and forgot to lock their screen.

**Trigger Conditions:**
- Active window belongs to a core industry application (VS Code, Figma, etc.)
- $I_D == 0$ AND $S_V == 0$ for **> 180 seconds**

**Action:**
- Immediately shift state to `"Idle_Away"` ✅
- Halt accumulation of productive work minutes
- Do not credit this time to Deep Work totals

---

### Protocol 4 — Rewriting History (Retroactive State Correction)
**Scenario:** The user was in an "Unknown / Uncertain" state (zero input, 5 minutes, inside a primary app). We can only know *why* once we see what they do next.

**Branch A — Retroactive Deep Work:**
- User resumes typing with $I_D > 20$ inside a `Core_Tool`
- → Rewrite previous 5 minutes of database records to `"Deep Work"` ✅

**Branch B — Retroactive Idle:**
- User moves the mouse and opens a `Leisure`-tagged app, OR system goes to sleep
- → Rewrite previous 5 minutes of database records to `"Idle_Away"` ✅

---

## 🤖 Local Machine Learning Pipeline

### Feature Engineering Vector
Every 60 seconds, the engine produces a 5-dimensional feature array:

| Feature | Description |
|---|---|
| `f0` | Mean Interaction Density ($I_D$) over the last 5 minutes |
| `f1` | Mean Scroll Velocity ($S_V$) over the last 5 minutes |
| `f2` | Context Switching Entropy ($E_C$) |
| `f3` | Core Tool Presence Ratio (0.0 → 1.0, time inside core apps) |
| `f4` | Time-of-Day Float Index (e.g., `14.5` = 2:30 PM) |

### The Model
- **Algorithm:** Random Forest Classifier (`scikit-learn`)
- **Format:** Serialized `.joblib` binary file (~5MB on disk)
- **Execution:** Single CPU thread, fully offline inference

### Autonomous Retraining Daemon
The model starts in pure inference mode, guided by the rule engine. A background thread monitors `behavioral_sessions`:

```
New rows added ≥ 100   OR   7 calendar days elapsed
           │
           ▼
Extract historical feature matrices
           │
           ▼
Filter rows verified by user corrections (high/low risk labeled)
           │
           ▼
Run local .fit() on background thread
           │
           ▼
Hot-swap the active .joblib classifier file
           │
           ▼
Resume inference — NO app restart needed
```

---

## 🧠 Confidence-Aware Fusion Engine

The final Attention Risk Score blends the rule engine and ML model using a mathematically earned trust weight.

### The Formula

Let $N$ = total historical session count in local SQLite.

$$W_{\text{ml}} = \min\left(0.8,\ \frac{N}{500}\right)$$

$$W_{\text{rule}} = 1.0 - W_{\text{ml}}$$

$$\text{Final Attention Risk Score} = (R_{\text{rule}} \cdot W_{\text{rule}}) + (R_{\text{ml}} \cdot W_{\text{ml}})$$

### Trust Evolution Timeline

| Phase | $N$ Sessions | $W_{\text{ml}}$ | Behavior |
|---|---|---|---|
| **Cold Start** | $N < 50$ | ~0.0 | Rules dominate entirely |
| **Growing** | $50 \le N < 500$ | 0.0 → 0.8 (linear) | Gradual ML confidence build-up |
| **Fully Trained** | $N \ge 500$ | **0.8 (max)** | ML leads, 20% rule floor always maintained |

> The 20% rule floor is **permanent** — it ensures protocol overrides (DSA Exception, Comic Loophole, etc.) are always respected regardless of how confident the ML model becomes.

---

## 💬 Actionable Recommendation System

When the Final Attention Risk Score exceeds **0.75 continuously for 3 minutes**, a structured alert JSON is generated:

```json
{
  "alert_trigger": "Attention_Fragmentation_High",
  "primary_cause": "Frequent context switching detected between Core Coding and Visual Social Media feeds over the past 4 minutes.",
  "actionable_prompt": "Your attention pattern is currently breaking up. Consider minimizing open browser tabs and staying inside your editor layout. It typically takes 3 minutes of quiet work to re-enter deep focus.",
  "suggested_action": "Minimize Distracting Processes"
}
```

This replaces generic percentage-based warnings with **diagnosed, specific, and actionable** guidance.

---

## 🗺️ Implementation Roadmap

### Task Sequence 1 — The Sidecar Foundation
- [ ] Python background event collector loop (1-second poll, 5-second DB write)
- [ ] `pywin32` / `AppKit` active window querying integration
- [ ] `pynput` global mouse/keyboard delta capture (privacy-safe — no key content)
- [ ] `WindowActivityRepository` class wrapping all SQLite operations

### Task Sequence 2 — Mathematical Feature Extractor
- [ ] Rolling $E_C$ (Context Switching Entropy) pipeline
- [ ] $S_V$ (Scroll Velocity) and $I_D$ (Interaction Density) calculators
- [ ] Rule Engine module with all 4 Loophole Resolution Protocols
- [ ] Retroactive state rewriting logic for Protocol 4

### Task Sequence 3 — Local AI Integration
- [ ] scikit-learn Random Forest training manager module
- [ ] `joblib` model serialization and hot-swap mechanism
- [ ] Autonomous retraining daemon (100 rows / 7-day trigger)
- [ ] Confidence-aware fusion weight calculator ($W_{\text{ml}}$ / $W_{\text{rule}}$)

### Task Sequence 4 — Desktop Interface Layer
- [ ] Tauri + React workspace initialization
- [ ] Local WebSocket / HTTP server in Python sidecar (randomized port)
- [ ] Real-time attention score dashboard component
- [ ] Active session timeline log view
- [ ] Local model training status indicator
- [ ] Alert notification component (structured JSON rendering)

---

## 📁 Project Structure

```
AttentionLens/
├── src-tauri/                  # Tauri native desktop wrapper
│   ├── src/
│   │   └── main.rs             # Tauri entry point, sidecar process spawner
│   └── tauri.conf.json         # App config, sidecar permissions
│
├── frontend/                   # React UI
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard/      # Real-time attention score view
│   │   │   ├── Timeline/       # Historical session log
│   │   │   ├── AlertBanner/    # Structured alert renderer
│   │   │   └── ModelStatus/    # ML training state indicator
│   │   ├── hooks/
│   │   │   └── useAttentionSocket.ts  # WebSocket connection hook
│   │   └── App.tsx
│   └── package.json
│
├── engine/                     # Python sidecar process
│   ├── main.py                 # Entry point, starts all background threads
│   ├── tracker/
│   │   ├── window_hook.py      # pywin32/AppKit active window polling
│   │   └── input_listener.py   # pynput global input delta capture
│   ├── repository/
│   │   └── activity_repository.py  # ALL SQLite operations (Repository Pattern)
│   ├── engine/
│   │   ├── behavior_engine.py  # I_D, S_V, E_C, C_D calculators
│   │   ├── rule_engine.py      # 4 Loophole Resolution Protocols
│   │   ├── feature_engineer.py # f0–f4 feature vector builder
│   │   ├── ml_model.py         # Random Forest inference + hot-swap
│   │   ├── retraining_daemon.py# Background retraining thread
│   │   └── fusion_engine.py    # W_ml / W_rule blending + final score
│   ├── server/
│   │   └── api_server.py       # Local WebSocket / HTTP server (IPC bridge)
│   └── requirements.txt
│
├── data/
│   └── attentionlens.db        # Local SQLite database (auto-created)
│
├── models/
│   └── attention_classifier.joblib  # Trained RF model (auto-generated)
│
└── README.md
```

---

## 🔒 Privacy Guarantee

AttentionLens is built on a strict **local-first, privacy-by-architecture** principle:

- ✅ **No key content is ever recorded.** `pynput` captures only *counts* of keystrokes — never which keys were pressed.
- ✅ **No screenshots or screen content is captured.**
- ✅ **Zero network calls.** The app has no outbound connections, no telemetry, no analytics.
- ✅ **Your data never leaves your machine.** The SQLite database and ML model file live only on your local disk.
- ✅ **You own your model.** The `.joblib` classifier is trained entirely on your personal behavioral history and stored locally.

---

## 👥 Team

Built as a Final Year Project exploring the intersection of **behavioral computing**, **local AI personalization**, and **privacy-preserving productivity tools**.

---

*AttentionLens — Know where your attention really goes.*
