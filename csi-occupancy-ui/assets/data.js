/* 由 _work/build_data.py 生成，勿手改。源：C:/Users/jwlhl/Desktop/大一/项目制/项目四/.deepworks/tmp/model_v2/Model_v2/CSI_Model_v2/results */
window.CSI_DATA = {
  "meta": {
    "schema": 2,
    "dataset": {
      "id": "CSI_Model_v2",
      "name": "6B514 批次 1",
      "task": "effective_zone_occupancy",
      "device": "c5628c",
      "room": "6B514",
      "subcarriers": 64,
      "sampleRate": 100,
      "files": 15,
      "frames": 36117,
      "durationSec": 362.79
    },
    "model": {
      "id": "csi-rf-v2",
      "name": "RandomForest v2",
      "algo": "RandomForest",
      "trees": 200,
      "maxDepth": 5,
      "minLeaf": 3,
      "windowSec": 2.0,
      "trimSec": 1.0,
      "runtime": "Python 3.12.14 · sklearn 1.8.0"
    },
    "accuracy": 0.7794117647058824,
    "balanced": 0.7735930735930736,
    "baseline": 0.5147058823529411,
    "trainWindows": 82,
    "testWindows": 68,
    "confusion": {
      "tn": 19,
      "fp": 14,
      "fn": 1,
      "tp": 34
    },
    "perFile": {
      "玩电脑（3）.jsonl": {
        "windows": 12,
        "accuracy": 1.0
      },
      "空场无人（2）.jsonl": {
        "windows": 12,
        "accuracy": 0.16666666666666666
      },
      "设备旁挥手(2).jsonl": {
        "windows": 10,
        "accuracy": 1.0
      },
      "走动（3）.jsonl": {
        "windows": 13,
        "accuracy": 0.9230769230769231
      },
      "门口走.jsonl": {
        "windows": 10,
        "accuracy": 1.0
      },
      "风扇无人（3).jsonl": {
        "windows": 11,
        "accuracy": 0.6363636363636364
      }
    },
    "limits": [
      "Labels assigned from user-confirmed filenames and scene context; exact transitions are not video-verified.",
      "Only one device, room and collection day; only two empty-room recordings.",
      "Target is occupancy within the designated effective zone, not the whole room. Fan-only and outside-door movement are negative. No verified long stationary/sleeping-person evaluation.",
      "This batch was previously inspected and evaluated. Holdout results are development evidence, not a new blind final test. Zone boundary coordinates remain unspecified.",
      "Occupancy score is not a calibrated probability. Architecture and hyperparameters unchanged from v1; no tuning on this evaluation."
    ],
    "status": "development_evaluation_not_final",
    "generated": {
      "at": "2026-10-29 18:01",
      "source": "C:\\Users\\jwlhl\\Desktop\\大一\\项目制\\项目四\\.deepworks\\tmp\\model_v2\\Model_v2\\CSI_Model_v2\\results",
      "windows": 68
    }
  },
  "windows": [
    {
      "f": "玩电脑（3）.jsonl",
      "s": 1.0,
      "e": 3.0,
      "y": 1,
      "sc": 0.6333
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 3.0,
      "e": 5.0,
      "y": 1,
      "sc": 0.7315
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 5.0,
      "e": 7.0,
      "y": 1,
      "sc": 0.6222
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 7.0,
      "e": 9.0,
      "y": 1,
      "sc": 0.7156
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 9.0,
      "e": 11.0,
      "y": 1,
      "sc": 0.7602
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 11.0,
      "e": 13.0,
      "y": 1,
      "sc": 0.6445
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 13.0,
      "e": 15.0,
      "y": 1,
      "sc": 0.7473
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 15.0,
      "e": 17.0,
      "y": 1,
      "sc": 0.987
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 17.0,
      "e": 19.0,
      "y": 1,
      "sc": 0.8233
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 19.0,
      "e": 21.0,
      "y": 1,
      "sc": 0.8446
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 21.0,
      "e": 23.0,
      "y": 1,
      "sc": 0.636
    },
    {
      "f": "玩电脑（3）.jsonl",
      "s": 23.0,
      "e": 25.0,
      "y": 1,
      "sc": 0.5945
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 1.0,
      "e": 3.0,
      "y": 0,
      "sc": 0.7055
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 3.0,
      "e": 5.0,
      "y": 0,
      "sc": 0.6032
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 5.0,
      "e": 7.0,
      "y": 0,
      "sc": 0.645
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 7.0,
      "e": 9.0,
      "y": 0,
      "sc": 0.6954
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 9.0,
      "e": 11.0,
      "y": 0,
      "sc": 0.7329
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 11.0,
      "e": 13.0,
      "y": 0,
      "sc": 0.6769
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 13.0,
      "e": 15.0,
      "y": 0,
      "sc": 0.7139
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 15.0,
      "e": 17.0,
      "y": 0,
      "sc": 0.6811
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 17.0,
      "e": 19.0,
      "y": 0,
      "sc": 0.7193
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 19.0,
      "e": 21.0,
      "y": 0,
      "sc": 0.2411
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 21.0,
      "e": 23.0,
      "y": 0,
      "sc": 0.4218
    },
    {
      "f": "空场无人（2）.jsonl",
      "s": 23.0,
      "e": 25.0,
      "y": 0,
      "sc": 0.6875
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 1.0,
      "e": 3.0,
      "y": 1,
      "sc": 0.8742
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 3.0,
      "e": 5.0,
      "y": 1,
      "sc": 0.7006
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 5.0,
      "e": 7.0,
      "y": 1,
      "sc": 0.7883
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 7.0,
      "e": 9.0,
      "y": 1,
      "sc": 0.7851
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 9.0,
      "e": 11.0,
      "y": 1,
      "sc": 0.8196
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 11.0,
      "e": 13.0,
      "y": 1,
      "sc": 0.9537
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 13.0,
      "e": 15.0,
      "y": 1,
      "sc": 0.9078
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 15.0,
      "e": 17.0,
      "y": 1,
      "sc": 0.9076
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 17.0,
      "e": 19.0,
      "y": 1,
      "sc": 0.8998
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "s": 19.0,
      "e": 21.0,
      "y": 1,
      "sc": 0.9512
    },
    {
      "f": "走动（3）.jsonl",
      "s": 1.0,
      "e": 3.0,
      "y": 1,
      "sc": 0.8702
    },
    {
      "f": "走动（3）.jsonl",
      "s": 3.0,
      "e": 5.0,
      "y": 1,
      "sc": 0.4966
    },
    {
      "f": "走动（3）.jsonl",
      "s": 5.0,
      "e": 7.0,
      "y": 1,
      "sc": 0.7802
    },
    {
      "f": "走动（3）.jsonl",
      "s": 7.0,
      "e": 9.0,
      "y": 1,
      "sc": 0.6747
    },
    {
      "f": "走动（3）.jsonl",
      "s": 9.0,
      "e": 11.0,
      "y": 1,
      "sc": 0.8867
    },
    {
      "f": "走动（3）.jsonl",
      "s": 11.0,
      "e": 13.0,
      "y": 1,
      "sc": 0.9765
    },
    {
      "f": "走动（3）.jsonl",
      "s": 13.0,
      "e": 15.0,
      "y": 1,
      "sc": 0.979
    },
    {
      "f": "走动（3）.jsonl",
      "s": 15.0,
      "e": 17.0,
      "y": 1,
      "sc": 0.9012
    },
    {
      "f": "走动（3）.jsonl",
      "s": 17.0,
      "e": 19.0,
      "y": 1,
      "sc": 0.8218
    },
    {
      "f": "走动（3）.jsonl",
      "s": 19.0,
      "e": 21.0,
      "y": 1,
      "sc": 0.9775
    },
    {
      "f": "走动（3）.jsonl",
      "s": 21.0,
      "e": 23.0,
      "y": 1,
      "sc": 0.796
    },
    {
      "f": "走动（3）.jsonl",
      "s": 23.0,
      "e": 25.0,
      "y": 1,
      "sc": 0.964
    },
    {
      "f": "走动（3）.jsonl",
      "s": 25.0,
      "e": 27.0,
      "y": 1,
      "sc": 0.9446
    },
    {
      "f": "门口走.jsonl",
      "s": 1.0,
      "e": 3.0,
      "y": 0,
      "sc": 0.1849
    },
    {
      "f": "门口走.jsonl",
      "s": 3.0,
      "e": 5.0,
      "y": 0,
      "sc": 0.4269
    },
    {
      "f": "门口走.jsonl",
      "s": 5.0,
      "e": 7.0,
      "y": 0,
      "sc": 0.4275
    },
    {
      "f": "门口走.jsonl",
      "s": 7.0,
      "e": 9.0,
      "y": 0,
      "sc": 0.3425
    },
    {
      "f": "门口走.jsonl",
      "s": 9.0,
      "e": 11.0,
      "y": 0,
      "sc": 0.3856
    },
    {
      "f": "门口走.jsonl",
      "s": 11.0,
      "e": 13.0,
      "y": 0,
      "sc": 0.3623
    },
    {
      "f": "门口走.jsonl",
      "s": 13.0,
      "e": 15.0,
      "y": 0,
      "sc": 0.4907
    },
    {
      "f": "门口走.jsonl",
      "s": 15.0,
      "e": 17.0,
      "y": 0,
      "sc": 0.257
    },
    {
      "f": "门口走.jsonl",
      "s": 17.0,
      "e": 19.0,
      "y": 0,
      "sc": 0.2763
    },
    {
      "f": "门口走.jsonl",
      "s": 19.0,
      "e": 21.0,
      "y": 0,
      "sc": 0.1461
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 1.0,
      "e": 3.0,
      "y": 0,
      "sc": 0.3789
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 3.0,
      "e": 5.0,
      "y": 0,
      "sc": 0.7023
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 5.0,
      "e": 7.0,
      "y": 0,
      "sc": 0.391
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 7.0,
      "e": 9.0,
      "y": 0,
      "sc": 0.3201
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 9.0,
      "e": 11.0,
      "y": 0,
      "sc": 0.4125
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 11.0,
      "e": 13.0,
      "y": 0,
      "sc": 0.2796
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 13.0,
      "e": 15.0,
      "y": 0,
      "sc": 0.296
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 15.0,
      "e": 17.0,
      "y": 0,
      "sc": 0.6514
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 17.0,
      "e": 19.0,
      "y": 0,
      "sc": 0.7423
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 19.0,
      "e": 21.0,
      "y": 0,
      "sc": 0.6352
    },
    {
      "f": "风扇无人（3).jsonl",
      "s": 21.0,
      "e": 23.0,
      "y": 0,
      "sc": 0.3831
    }
  ],
  "audit": [
    {
      "f": "玩电脑（1）.jsonl",
      "frames": 2431,
      "dur": 24.308632,
      "split": "train",
      "label": "1",
      "acc": 11
    },
    {
      "f": "玩电脑（2）.jsonl",
      "frames": 2539,
      "dur": 25.400645,
      "split": "train",
      "label": "1",
      "acc": 11
    },
    {
      "f": "玩电脑（3）.jsonl",
      "frames": 2797,
      "dur": 27.969031,
      "split": "test",
      "label": "1",
      "acc": 12
    },
    {
      "f": "空场无人（1）.jsonl",
      "frames": 2169,
      "dur": 21.679998,
      "split": "train",
      "label": "0",
      "acc": 9
    },
    {
      "f": "空场无人（2）.jsonl",
      "frames": 2728,
      "dur": 27.300289,
      "split": "test",
      "label": "0",
      "acc": 12
    },
    {
      "f": "设备旁挥手(2).jsonl",
      "frames": 2226,
      "dur": 22.549857,
      "split": "test",
      "label": "1",
      "acc": 10
    },
    {
      "f": "设备旁挥手（1）.jsonl",
      "frames": 2561,
      "dur": 25.600224,
      "split": "train",
      "label": "1",
      "acc": 11
    },
    {
      "f": "走动（1）.jsonl",
      "frames": 2690,
      "dur": 26.909611,
      "split": "train",
      "label": "1",
      "acc": 12
    },
    {
      "f": "走动（2）.jsonl",
      "frames": 1757,
      "dur": 17.561029,
      "split": "train",
      "label": "1",
      "acc": 7
    },
    {
      "f": "走动（3）.jsonl",
      "frames": 2841,
      "dur": 28.420161,
      "split": "test",
      "label": "1",
      "acc": 13
    },
    {
      "f": "起身出教室.jsonl",
      "frames": 1890,
      "dur": 18.898002,
      "split": "exclude",
      "label": "",
      "acc": 0
    },
    {
      "f": "门口走.jsonl",
      "frames": 2339,
      "dur": 23.971324,
      "split": "test",
      "label": "0",
      "acc": 10
    },
    {
      "f": "风扇无人（1）.jsonl",
      "frames": 2280,
      "dur": 23.178887,
      "split": "train",
      "label": "0",
      "acc": 10
    },
    {
      "f": "风扇无人（2）.jsonl",
      "frames": 2482,
      "dur": 24.986874,
      "split": "train",
      "label": "0",
      "acc": 11
    },
    {
      "f": "风扇无人（3).jsonl",
      "frames": 2387,
      "dur": 24.057335,
      "split": "test",
      "label": "0",
      "acc": 11
    }
  ]
};
