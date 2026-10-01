"""스캔 이미지를 기준 템플릿 좌표계로 정렬한다.

ORB 특징점은 회전 불변이므로 180° 뒤집힌 스캔도 호모그래피 하나로 바로잡힌다.
특징점 계산은 1/2 축소본에서 하고, 결과 호모그래피로 원본 해상도를 warp한다.
"""

from dataclasses import dataclass

import cv2
import numpy as np

SCALE = 0.5
MIN_INLIERS = 150
MAX_SCALE_DEV = 0.05  # 스캔 배율이 템플릿과 5% 이상 다르면 정합 실패로 본다


@dataclass
class AlignResult:
    image: np.ndarray  # 템플릿 크기로 정렬된 이미지
    inliers: int
    rotation: float  # 도(deg), 180 근처면 뒤집힌 스캔
    ok: bool


class Aligner:
    def __init__(self, template: np.ndarray, n_features: int = 4000):
        self.shape = template.shape[:2]
        self.orb = cv2.ORB_create(n_features)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.kp_t, self.des_t = self._features(template)
        s = np.diag([SCALE, SCALE, 1.0])
        self._s, self._s_inv = s, np.linalg.inv(s)

    def _features(self, img: np.ndarray):
        small = cv2.resize(img, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
        return self.orb.detectAndCompute(small, None)

    def align(self, img: np.ndarray) -> AlignResult:
        h, w = self.shape
        kp, des = self._features(img)
        H, inliers = None, 0
        if des is not None and len(kp) >= 10:
            pairs = self.matcher.knnMatch(des, self.des_t, k=2)
            good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
            if len(good) >= 10:
                src = np.float32([kp[m.queryIdx].pt for m in good])
                dst = np.float32([self.kp_t[m.trainIdx].pt for m in good])
                H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
                inliers = int(mask.sum()) if mask is not None else 0

        if H is None:
            return AlignResult(cv2.resize(img, (w, h)), inliers, 0.0, False)

        rotation = float(np.degrees(np.arctan2(H[1, 0], H[0, 0])))
        scale = float(np.hypot(H[0, 0], H[1, 0]))
        ok = inliers >= MIN_INLIERS and abs(scale - 1) < MAX_SCALE_DEV
        H_full = self._s_inv @ H @ self._s
        warped = cv2.warpPerspective(
            img, H_full, (w, h), flags=cv2.INTER_LINEAR, borderValue=255
        )
        return AlignResult(warped, inliers, rotation, ok)
