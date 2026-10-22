# MVP Product Requirements Document

# Wi-Fi Device-Based Presence Detection with Interference Mitigation
## First Version: Motion/No-Motion Research Prototype

**Document date:** October 15, 2026  
**Version:** 1.1  
**Target users:** Student project team and instructor  
**Operating environment:** Local computer; one fixed test room  
**Schedule:** To be determined

**Related document:** [Project Proposal](Project_Proposal.md), especially Section 3 (EV-01: external research; EV-02: instructor discussion with a translated written reply; EV-03: team scope decisions). No systematic tests have been completed.

## 1. Purpose

Build a working experimental pipeline that receives ESP32 CSI data, displays and saves it, supports spatial-response experiments, and enables our own trained model to classify motion/no motion.

The broader project aims to detect human occupancy, including during typing, resting, and sleeping, while rejecting non-human interference. This MVP establishes the data and motion-detection foundation; it does not promise those broader capabilities.

## 2. Output Meaning and Scope

- **Motion detected:** The model predicts movement in the defined test interval.
- **No motion detected:** The model predicts no movement in that interval.
- Moving people and moving non-human objects both count as motion for this MVP.
- A no-motion result must not be presented as proof that the room is unoccupied.
- The prediction interval and supported test conditions will be documented after initial trials.

The four essential objectives are sensing-coverage investigation, location-response analysis, our own trained motion detector, and reusable data recording. All four are required; neither automated mapping nor automated video labeling is required.

## 3. Users and Basic Workflow

The project team conducts experiments, labels data, trains models, and examines results. The instructor reviews the scope, evidence, and prototype.

1. Set up hardware and record device and test positions.
2. Start computer-side CSI acquisition and smartphone video recording.
3. Test movement and no-motion conditions at documented positions.
4. Save raw data and establish its time correspondence with the video.
5. Label intervals and compare responses across positions.
6. Train a local model and evaluate it using independent test recordings.
7. Run the trained model on newly received CSI data; save predictions and review errors.

An initial collection period may be needed before the first prediction. Timing requirements remain to be agreed.

## 4. Inputs and Outputs

| Category | Required content |
| --- | --- |
| Inference input | Hardware-derived CSI numerical data parsed from received raw bytes; no video input |
| Experimental reference | Smartphone video and its documented relationship to the CSI timeline |
| Context | Experiment ID, timing, device positions, activity position, object, action, and recording references |
| Live output | CSI curves and model motion/no-motion predictions when a trained model is available |
| Saved output | Raw recordings, metadata, labels, predictions, model artifacts, and evaluation results |
| Analysis output | Tested-position map, coverage observations, and position-response comparisons |

Curves are a visual representation of the CSI data. Curve screenshots are not the assumed model input.

## 5. Functional Requirements

| ID | Requirement |
| --- | --- |
| FR-01 | Receive and parse the available raw CSI output from the ESP32 setup on the computer. Confirm the packet format and available fields before implementation. |
| FR-02 | Display readable CSI curves during acquisition without preventing raw-data recording. The displayed channels or derived quantities must be identified. |
| FR-03 | Start and stop recording and save raw data that can be reopened for later analysis and training. |
| FR-04 | Associate every session with its experiment ID, timestamps or time index, device placement, activity position, object type, action, and video reference. A room sketch or named positions may be used instead of exact coordinates. |
| FR-05 | Document video-to-CSI time correspondence sufficient for labeling and evaluation. The alignment method and acceptable error remain to be agreed; a dedicated timer is optional pending a decision. |
| FR-06 | Support motion/no-motion labels linked to data intervals. Manual video review and annotation are acceptable. Flag ambiguous intervals and document how they are handled. |
| FR-07 | Support coverage experiments and produce a map or annotated room sketch with tested positions, response observations, and links to supporting recordings. Manual report preparation is acceptable. |
| FR-08 | Support comparisons of responses at different positions, including router–ESP32 line regions and edges where applicable. Record comparable actions and relevant conditions; do not assume which region responds more strongly. |
| FR-09 | Train our own motion/no-motion model locally using the collected CSI data and labels. Save the model and the preprocessing configuration needed to reproduce its inputs. |
| FR-10 | Load the trained model and run inference locally on newly received CSI data. Retain predictions with their corresponding intervals. Also support evaluation of saved test recordings. |
| FR-11 | Support retraining with additional sessions and retain enough model-version and dataset information to compare iterations. |
| FR-12 | Keep training, validation where used, and final-test sessions separate. Overlapping windows from the same recording must not cross these partitions. Fit preprocessing using training data only. |
| FR-13 | Compare test predictions with video-derived reference labels. Report correct classifications, false positives, missed motion, class counts, and defined evaluation metrics. |

## 6. Data Organization and Evaluation

Each session must be traceable from raw data to metadata, reference video, labels, and predictions. The file format and folder naming convention remain implementation choices. Preserve raw recordings; derived data should be distinguishable from original data.

For binary evaluation, treat motion as the positive class:
- **Accuracy:** Correct predictions divided by all evaluated predictions.
- **False-positive rate:** No-motion intervals predicted as motion, divided by all reference no-motion intervals.
- **Missed-motion rate:** Motion intervals predicted as no motion, divided by all reference motion intervals.

State the prediction unit, interval length, class counts, and excluded intervals. If a denominator is zero, report that metric as not applicable. Include both motion and no-motion cases in the final test plan.

Do not reuse final-test results repeatedly to tune the model. If they influence model changes, use a new held-out test session for the next final evaluation.

## 7. Acceptance Criteria

| Objective | Required acceptance evidence |
| --- | --- |
| Sensing coverage | A documented setup and tested-position map, with responsive and weak-response observations traceable to recordings. Conclusions are limited to tested conditions. |
| Position-dependent responses | Comparisons across documented positions using stated activities and conditions, with supporting curves or numerical summaries. An absent difference is a valid experimental finding. |
| Own trained model | A saved model and reproducible local training procedure; demonstrated inference on newly acquired data; independent-session evaluation against video labels, including false positives and missed motion. |
| Reusable data | Saved raw recordings can be reopened and matched to metadata, video references, labels, and predictions. |
| Video association | The alignment procedure is documented and checked on reference events before labels are used. |
| Iteration | The team can train a revised model with additional data and identify which data and model version produced each evaluation. |

Quantitative acceptance decisions are pending: accuracy and error-rate thresholds, test counts, durations, alignment tolerance, display latency, and inference response time. Agree and document these before final acceptance testing. This PRD does not impose zero packet loss, millisecond synchronization accuracy, a 500 ms display target, or a five-minute setup target.

## 8. Non-Functional Requirements

- Training and inference run on the team's own computer.
- The interface may be a desktop application or locally hosted browser interface. No public hosting is required.
- Prefer free/open-source tools and existing equipment; no paid service or additional purchase is assumed.
- Keep acquisition, processing, and modeling sufficiently separable to support model iteration.
- Make recording interruptions, invalid packets, and missing data identifiable where detected; document their handling rather than silently treating them as valid samples.
- Preserve experiment data and model records in a readable, documented format.
- Keep smartphone reference videos local to the experiment workflow; no cloud video upload is required.

## 9. Business Rules, Edge Cases, and Model Boundaries

| ID | Condition | Required behavior |
| --- | --- | --- |
| BR-01 | No device connection or no valid CSI | Show unavailable/waiting status; do not output no motion as a substitute for missing data |
| BR-02 | Invalid packet or acquisition interruption | Flag the detected issue, retain already saved valid data, and identify affected intervals; do not silently fill them with valid-looking samples |
| BR-03 | Start recording while already recording | Keep a single active recording per acquisition stream; do not create an accidental duplicate or overwrite |
| BR-04 | Missing required session context | Request completion before declaring the session ready for labeled dataset use; keep captured raw data recoverable |
| BR-05 | Existing output filename | Preserve the existing recording; require a distinct name or explicit overwrite confirmation |
| BR-06 | Missing video, uncertain event, or unverified time alignment | Mark the interval/session as unlabeled or uncertain; exclude it from supervised training and scored testing until resolved |
| BR-07 | No model, incompatible input, or inference failure | Display model unavailable/error and preserve raw acquisition; do not invent a binary prediction |
| BR-08 | Retraining or model replacement | Preserve the prior model and its evaluation; identify the new version and avoid silently switching models during a session |
| BR-09 | Local access | No application accounts or remote roles are required. The experiment operator controls local files through the computer's normal access permissions |
| BR-10 | Video capture | Inform participating team members, avoid unrelated people, and keep reference videos local; sharing requires a separate team decision |

The model may access parsed CSI and its required preprocessing configuration. Video and object/action labels are evaluation references, not inference inputs. Predictions are experimental outputs, not triggers for unattended lighting or other physical actions in this MVP.

## 10. Requirement Verification Matrix

These are planned checks, not completed test results. Retain the evidence and outcome for each check at demonstration.

| Test ID | Requirement | Success and failure checks |
| --- | --- | --- |
| AT-01 | FR-01 | Receive and parse a valid sample; test unavailable hardware and an invalid packet (BR-01/02) |
| AT-02 | FR-02 | Display identified curves during recording; verify a plot interruption does not silently invalidate saved data |
| AT-03 | FR-03 | Start, stop, reopen, and compare a recording; test duplicate start and existing filename (BR-03/05) |
| AT-04 | FR-04 | Match data to complete metadata; detect missing required context (BR-04) |
| AT-05 | FR-05 | Document alignment and check visible reference events; flag unresolved alignment (BR-06) |
| AT-06 | FR-06 | Retrieve labels by interval; ensure uncertain/video-missing intervals are not scored as certain labels |
| AT-07 | FR-07 | Inspect tested-position map and trace each observation to supporting data |
| AT-08 | FR-08 | Compare documented positions under stated conditions; retain results even if no consistent difference is found |
| AT-09 | FR-09 | Train, save, and reload the team's model and preprocessing configuration |
| AT-10 | FR-10 | Predict from new CSI and saved test data; test no model and incompatible input (BR-07) |
| AT-11 | FR-11 | Retrain on additional data and distinguish model versions without overwriting prior evidence |
| AT-12 | FR-12 | Audit session lists and preprocessing fitting; reject a partition containing the same recording across train and final test |
| AT-13 | FR-13 | Recompute metrics from predictions and labels; verify class counts, exclusions, and undefined-denominator handling |

## 11. User Value and Demonstration Readiness

The team should be able to complete the end-to-end workflow in Section 3 using the documented local procedure and recover a prior experiment without losing its context. Demonstrate that recordings can be reused, position findings can be traced to data, and model iterations can be compared. These assess research usefulness; AT-01 through AT-13 assess specified behavior.

The MVP is ready for demonstration when all four objectives have evidence, the applicable acceptance checks pass, known failures are disclosed, and the performance/timing targets agreed before testing are assessed. Any unmet target is reported as incomplete rather than silently removed. No claim of complete occupancy detection is required.

## 12. Available Hardware and Constraints

Two ESP32 boards, one router, a smartphone, and a computer are available. The exact ESP32 roles and whether both must be active together are undecided. Experiments are limited to one fixed room and the documented configuration.

Specific operating-system support, firmware changes, communication protocols, storage formats, model families, and software libraries are not prescribed here. Existing acquisition capabilities should be checked before selecting implementation tools.

## 13. Out of Scope

Stationary occupancy and interference classification require a later dataset and research effort. Cross-room/vendor guarantees and multi-AP fusion expand beyond the fixed-room baseline. Device-side inference and smart-home integration add deployment complexity. Public/mobile interfaces, automated labeling/mapping, and a dedicated timer are unnecessary to establish the current experimental workflow; the timer remains an optional future decision.

- Reliable human occupancy detection during rest or sleep.
- Human-versus-fan or other object-type classification.
- Fine-grained activity recognition.
- Comprehensive interference rejection.
- Multiple-AP fusion and cross-vendor or cross-room guarantees.
- Model inference on ESP32, an AP, or a router.
- Smart-home integration, a public website, or a mobile app.
- Mandatory automated video labeling, mapping, or a dedicated timer.
- Personnel assignments.

## 14. Open Decisions and Dependencies

| Topic | Current position |
| --- | --- |
| ESP32 roles and packet access | Verify current firmware and available data output |
| Transport and storage | To be determined after acquisition checks |
| Interface and operating system | Local computer; precise implementation to be determined |
| Synchronization | Time association required; method, tolerance, and timer decision pending |
| Experiment design | Positions, activities, repetitions, durations, and motion definitions to be finalized |
| Modeling | Preprocessing, input window, model family, and selection procedure pending |
| Acceptance thresholds | To be agreed before final testing |
| Schedule | To be determined |
| Course format compliance | Reviewed against the October 14, 2026 course guidelines |

## 15. Handoff Summary

Implement the four MVP objectives without interpreting motion detection as occupancy detection. Use video for reference labels only. Preserve raw data and experiment traceability. Train and run the model on the computer, allow retraining, and evaluate using independent sessions. Treat unconfirmed implementation suggestions as options.

The companion Project Proposal explains the wider research direction. This PRD defines the first-version commitments. Prepared against the course Project Documentation Guidelines dated October 14, 2026. Agree the unresolved acceptance targets before final testing.



## 16. Open-Item Resolution Actions

Personnel assignments belong in the proposal, not this PRD. The following actions define how remaining decisions will be resolved.

| Open item | Next action / decision checkpoint |
| --- | --- |
| Problem evidence | External research and instructor discussion are recorded as EV-01 and EV-02 in proposal Section 3; retain original source references, access dates, research records, and the original instructor correspondence; add findings as experiments proceed |
| ESP32 roles and transport | Inspect current firmware/output and perform a receive-and-save trial before the main collection |
| Storage and interface | Choose after demonstrating that a raw sample can be displayed, saved, and reopened |
| Alignment and timer | Pilot simultaneous video/CSI capture; compare candidate alignment methods and document achievable tolerance before labeling |
| Experiment plan | Define positions, actions, motion interval rules, durations, and repetitions before main collection |
| Model and preprocessing | Compare suitable baseline options using training/validation sessions; freeze selection before final testing |
| Quantitative targets | Agree realistic performance and timing thresholds with the team/instructor after pilots and before final testing |
| Test location | Room 6B514 |
| Room access and setup reproducibility | Fixed time slots are available each week; device positions can be reproduced |
| Available time and schedule | 3–4 hours per week; schedule to be determined |

**Revision note:** Version 1.1 aligns the initial draft with course requirements by adding evidence references, failure rules, requirement-linked acceptance checks, demonstration readiness, and explicit resolution actions. It does not add occupancy detection to the MVP.
