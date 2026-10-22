# Project Proposal
## Wi-Fi Device-Based Presence Detection with Interference Mitigation

**Chinese title:** Wi-Fi 设备存在检测抗干扰  
**Date:** October 15, 2026 | **Version:** 1.1 | **Stage:** Project initiation  
**Related document:** [MVP PRD](MVP_PRD.md)

## 1. Summary

Investigate Wi-Fi CSI-based room occupancy detection, beginning with a local motion-detection prototype and spatial-response experiments in one fixed room.

The long-term goal is to report human presence during walking, typing, resting, and sleeping, while rejecting non-human interference such as a moving fan. Recognizing the specific human activity is not required. These are research goals, not achieved capabilities or first-MVP commitments.

## 2. Problem, Users, and Existing Workflow

The immediate users are the student project team and instructor. The team needs a repeatable way to observe CSI, investigate where movement produces a response, retain labeled recordings, and evaluate its own model. Future occupancy information could support lighting and air-conditioning control in general rooms; demand and deployment benefits have not been validated.

The starting approach is to inspect hardware-derived CSI curves using existing tools and compare observations with what happens in the room. This alone does not establish sensing coverage, supply an organized labeled dataset, or demonstrate motion classification on new recordings. The proposed MVP connects those tasks into a reusable experimental workflow.

Alternative sensing approaches to investigate include PIR, millimeter-wave radar, camera-based detection, and existing Wi-Fi sensing systems. No comparative performance, cost advantage, or competitor limitation is claimed without evidence. The current gap is the team's need for an inspectable, locally trainable CSI experiment pipeline.

## 3. Evidence and Investigation Status

**EV-01 — External research:** External evidence was collected and compiled by project team members in October 2026 through online searches of user communities for similar products, media reviews, and official policies, including web searches, comparisons with original texts, and cross-verification. According to the team's research record, all data and quotations were checked word for word against their original sources, and no unverified information was used.

**EV-02 — Instructor discussion:** The team shared its proposed target users and application directions with the instructor: occupancy-based energy saving in hotels, schools, and offices; smart-home automation; elderly care; library/study-room seat sensing; and privacy-conscious home security. The instructor responded positively, identified these as potential applications, and noted that some ideas had already been implemented in Huawei commercial equipment. This records the instructor's feedback; it is not an independent verification of a particular commercial product's capabilities or proof of this prototype's performance. The additional applications remain long-term directions and do not expand the first MVP.

**Instructor's reply (English translation of the Chinese message):**

> Yes, these ideas are all quite good. They are all potential applications. Some of these ideas have already been implemented in Huawei's commercial equipment.

*Source: the instructor's written reply in the conversation record supplied by the team. The supplied record does not show a calendar date.*

**EV-03 — Team scope decisions:** The team has selected a fixed-room first MVP, local computer training and inference, video-assisted labeling, and four initial objectives. Source: project planning discussion, October 15, 2026. These are planning decisions, not experimental findings.

No systematic project tests or measured performance results have been completed. Coverage, position effects, synchronization feasibility, and model performance remain unverified. In particular, stronger responses near the router–ESP32 line are a hypothesis. External research and instructor feedback inform the project direction; experimental validation remains planned work.

## 4. Smallest Useful Solution and Value

| MVP objective | Reviewable output and value |
| --- | --- |
| G-01: Sensing coverage | Tested-position map and response records show where the current setup responds to tested movement |
| G-02: Location responses | Comparable recordings and summaries reveal how position affects the signal |
| G-03: Own motion model | A locally trained, saved model predicts motion/no motion on new CSI data |
| G-04: Reusable data | Raw bytes, displayed curves, metadata, video references, and labels support repeatable analysis and iteration |

The complete user task is: set up an experiment, receive and save CSI, record reference video, associate timelines, label intervals, analyze positions, train a model, and compare new predictions with video-confirmed events. Manual labeling, maps, and comparisons are acceptable.

Motion includes people and non-human objects. No motion does not establish that a room is unoccupied. Stationary-person detection, human-versus-fan classification, multi-AP fusion, cross-room generalization, and device-side inference are deferred to keep the initial experiment manageable.

## 5. Feasibility, Resources, and Risks

Available equipment: two ESP32 boards, one router, a smartphone, and the team's computer. Exact ESP32 roles remain open. The computer receives data, displays curves, saves recordings, and trains and runs the model. Video supplies reference labels only; normal inference uses CSI without video. Prefer free/open-source tools and existing equipment; no paid service or purchase is assumed.

- **Test location:** Room 6B514
- **Room access and ability to retain/reproduce device positions:** Fixed time slots are available each week; device positions can be reproduced.
- **Available project time per week:** 3–4 hours

The principal uncertainty is whether the available data and tested setup support repeatable motion/no-motion classification. Investigate through pilot acquisition, position tests, and independent-session evaluation. Other risks include recording interruptions, weak spatial responses, video misalignment, uncertain labels, and leakage between related training/test samples. Record interruptions, document weak areas, check time alignment, flag uncertain labels, and separate recording sessions for evaluation.

Tools, transport, storage, preprocessing, and model architecture will be selected after checking existing acquisition capabilities. Reliable video/data correspondence is necessary; a dedicated timer is undecided. Smartphone reference recordings should be limited to agreed experimental activity and kept local.

## 6. Team and Responsibilities

| Role | Member | Primary responsibility | Core reviewable outputs | MVP objectives |
| --- | --- | --- | --- | --- |
| L — Team lead | 倪世豫 | Coordination and quality review | Project plan; weekly meeting notes; consolidated project logs; integrated evaluation report | All |
| A — Hardware and firmware | 何储安 | Two ESP32 boards, router, and serial communication link | Flashing/setup guide reproducible by a newcomer within 30 minutes; link availability records; configuration snapshots | G-01 / G-02 |
| B — Data pipeline | 刘羽萱 | Acquisition scripts, storage, time alignment, and labeling | Saved recordings that can be reopened for spot checks; alignment-tolerance experiments; labeling agreement of at least 90% | G-04 |
| C — Experiment execution | 王悦为 | Test-position design, action scripts, and on-site coordination | M-02 experiment plan; experiment logs; labeled dataset | G-01 / G-02 / G-03 |
| D — Model evaluation | 颜子程 | Preprocessing, training, and data-leakage prevention | Recording-level dataset-splitting script; experiment records; baseline model report | G-03 |

These responsibilities apply throughout the project. Listed outputs and numerical targets are planned commitments, not completed results. The team will document the setup conditions for the 30-minute reproducibility check and the sample, reviewers, and calculation method for the labeling-agreement check before assessment.

## 7. Milestones and Evaluation

| Milestone | Reviewable output | Planned time |
| --- | --- | --- |
| M-01: Scope and acquisition review | Direct evidence record, confirmed hardware output, saved/reopened sample | To be determined |
| M-02: Characterization | Position-based recordings, coverage map, response comparisons | To be determined |
| M-03: Dataset and initial model | Video-associated labels, session partitions, saved locally trained model | To be determined |
| M-04: Independent demonstration | Live inference, test report, errors, limitations, and iteration records | To be determined |

The companion PRD links requirements to acceptance checks. Report accuracy, false-positive rate, and missed-motion rate with sample counts and definitions. Agree numerical thresholds, test counts, durations, and timing tolerances after pilot acquisition and before final testing. Independent testing measures the tested conditions and does not guarantee performance in other rooms.

## 8. Document Review

Prepared against Project Documentation Guidelines, course adaptation dated October 14, 2026. Retain the original source references, access dates, research records, and original instructor correspondence supporting Section 3. Confirm the pending schedule as planning progresses. Record later scope changes and actual verification outcomes rather than presenting planned capabilities as completed work.
