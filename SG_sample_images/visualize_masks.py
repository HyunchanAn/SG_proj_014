# ruff: noqa
import os
import sys
import numpy as np
import cv2
import torch

# 통합 모듈 경로 세팅
sys.path.insert(0, "E:/Github/SG_proj_003")
sys.path.append("E:/Github/SG_integration_002+003+007")
os.chdir("E:/Github/SG_integration_002+003+007")
torch.set_num_threads(1)

from deepdrop_sfe import AIContactAngleAnalyzer, DropletPhysics, PerspectiveCorrector
from vsams.analysis.surface_evaluator import SurfaceEvaluator
import vsams
print("VSAMS PATH IS:", vsams.__file__)
from src.seg.sam2_wrapper import SAM2BaseWrapper
from src.topo.depth_wrapper import DepthAnythingV2Wrapper

ORGANIZED_DIR = "E:/Github/SG_proj_014/SG_sample_images/organized"
OUTPUT_DIR = "E:/Github/SG_proj_014/SG_sample_images"

def draw_mask_overlay(image_rgb, mask, color=(0, 255, 0), alpha=0.4):
    """
    RGB 이미지 위에 불리언 마스크를 반투명 오버레이하고 빨간색 외곽선을 그림
    """
    overlay = image_rgb.copy()
    overlay[mask] = color
    
    # 블렌딩
    blended = cv2.addWeighted(image_rgb, 1 - alpha, overlay, alpha, 0)
    
    # 외곽선 그리기
    mask_u8 = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(blended, contours, -1, (255, 0, 0), 3) # 빨간색 외곽선
    
    return blended

def main():
    print("Starting visual mask verification generation...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # 모델 일괄 로드
    sfe_analyzer = AIContactAngleAnalyzer(device=device)
    corrector = PerspectiveCorrector()
    vsams_eval = SurfaceEvaluator()
    sam2_w = SAM2BaseWrapper()
    sam2_w.load_model(use_mobilesam=False)
    
    da_ckpt = "models/depth_anything_v2/depth_anything_v2_vits.pth"
    depth_w = DepthAnythingV2Wrapper(encoder="vits", checkpoint_path=da_ckpt, device=device)
    depth_w.load_model()
    
    for target_material in ["2B", "BA", "HL"]:
        for liquid in ["water", "glycerol"]:
            print(f"\nProcessing visual verify images for {target_material} ({liquid})...")
            
            # 파일 경로 정의
            liquid_path = os.path.join(ORGANIZED_DIR, f"{target_material}_{liquid}.jpg")
            reflect_path = os.path.join(ORGANIZED_DIR, f"{target_material}_reflect.jpg")
            depth_path = os.path.join(ORGANIZED_DIR, f"{target_material}_3d.jpg")
            
            # =========================================================================
            # [1] SFE 1단계: 동전 자동 검출 및 마스크 추출 시각화
            # =========================================================================
            if os.path.exists(liquid_path):
                bgr = cv2.imread(liquid_path)
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                
                # 동전 자동 검출
                box_arr, coin_info = sfe_analyzer.auto_detect_coin_candidate(bgr)
                if box_arr is not None:
                    # SAM 2로 동전 마스크 획득
                    sfe_analyzer.set_image(rgb)
                    coin_mask, _ = sfe_analyzer.predict_mask(box=box_arr)
                    
                    # 오버레이 이미지 그리기
                    overlay_coin = draw_mask_overlay(rgb, coin_mask, color=(0, 255, 0)) # 초록색 오버레이
                    
                    # 박스 표시
                    x1, y1, x2, y2 = map(int, box_arr)
                    cv2.rectangle(overlay_coin, (x1, y1), (x2, y2), (255, 255, 0), 4) # 노란색 사각형
                    
                    # 파일 저장 (E:\Github\SG_sample_images\organized 하위에 저장)
                    out_coin_path = os.path.join(ORGANIZED_DIR, f"{target_material}_{liquid}_verify_step1_coin.jpg")
                    cv2.imwrite(out_coin_path, cv2.cvtColor(overlay_coin, cv2.COLOR_RGB2BGR))
                    print(f"-> Saved: {out_coin_path}")
                    
                    # =========================================================================
                    # [2] SFE 2단계: 원근 보정 및 탑뷰(Top-view) 이미지 생성
                    # =========================================================================
                    H, warped_size, coin_warp, fitted = corrector.find_homography(bgr, coin_mask)
                    if H is not None:
                        warped_bgr = corrector.warp_image(bgr, H, warped_size)
                        warped_rgb = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2RGB)
                        
                        out_warp_path = os.path.join(ORGANIZED_DIR, f"{target_material}_{liquid}_verify_step2_topview.jpg")
                        cv2.imwrite(out_warp_path, warped_bgr)
                        print(f"-> Saved: {out_warp_path}")
                        
                        # =========================================================================
                        # [3] SFE 3단계: 탑뷰에서 액적 자동 감지 및 마스킹 오버레이 시각화
                        # =========================================================================
                        coin_cx, coin_cy, coin_r = coin_warp
                        coin_pad = coin_r * 0.15
                        exclude_box_warped = [
                            coin_cx - coin_r - coin_pad,
                            coin_cy - coin_r - coin_pad,
                            coin_cx + coin_r + coin_pad,
                            coin_cy + coin_r + coin_pad
                        ]
                        
                        # 액적 자동 검출
                        drop_box = sfe_analyzer.auto_detect_droplet_candidate(
                            warped_bgr, exclude_box=exclude_box_warped, coin_radius=coin_r
                        )
                        
                        if drop_box is not None:
                            # SAM 2로 액적 마스크 획득
                            sfe_analyzer.set_image(warped_rgb)
                            drop_mask, _ = sfe_analyzer.predict_mask(box=drop_box)
                            
                            # 액적 오버레이 그리기 (파란색 투명 마스크)
                            overlay_drop = draw_mask_overlay(warped_rgb, drop_mask, color=(0, 0, 255))
                            
                            # 액적 상자 표시
                            dx1, dy1, dx2, dy2 = map(int, drop_box)
                            cv2.rectangle(overlay_drop, (dx1, dy1), (dx2, dy2), (0, 255, 255), 4)
                            
                            out_drop_path = os.path.join(ORGANIZED_DIR, f"{target_material}_{liquid}_verify_step3_droplet.jpg")
                            cv2.imwrite(out_drop_path, cv2.cvtColor(overlay_drop, cv2.COLOR_RGB2BGR))
                            print(f"-> Saved: {out_drop_path}")
                        else:
                            print(f"-> Warning: Droplet auto detection failed for {target_material} ({liquid}).")
            
            # reflect 와 depth 는 시약 종류에 무관하므로 첫 번째 시약 루프(water)에서 1회만 생성
            if liquid == "water":
                # =========================================================================
                # [4] V-SAMS 마감 분석 영역 오버레이 시각화
                # =========================================================================
                if os.path.exists(reflect_path):
                    bgr_r = cv2.imread(reflect_path)
                    res_v = vsams_eval.analyze(bgr_r)
                    if "error" not in res_v:
                        overlay_finish = vsams_eval.get_overlay_image(bgr_r, res_v)
                        
                        out_finish_path = os.path.join(ORGANIZED_DIR, f"{target_material}_reflect_verify_finish.jpg")
                        overlay_finish.save(out_finish_path)
                        print(f"-> Saved: {out_finish_path}")
                        
                # =========================================================================
                # [5] SG-TERRA 3D 뎁스맵 추론 시각화
                # =========================================================================
                if os.path.exists(depth_path):
                    bgr_d = cv2.imread(depth_path)
                    rgb_d = cv2.cvtColor(bgr_d, cv2.COLOR_BGR2RGB)
                    
                    # 3D 분석을 위한 대략적인 타겟 분할 수행
                    h_d, w_d = rgb_d.shape[:2]
                    target_pts = np.array([[w_d // 2, h_d // 2]])
                    target_lbls = np.array([1])
                    mask_t = sam2_w.segment_target(rgb_d, prompt_points=target_pts, prompt_labels=target_lbls)
                    
                    # 뎁스맵 연산
                    dmap = depth_w.estimate_depth(rgb_d, mask=mask_t)
                    
                    # 뎁스 시각화 컬러맵 처리
                    d_vis = cv2.normalize(dmap, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    d_col = cv2.applyColorMap(d_vis, cv2.COLORMAP_INFERNO)
                    
                    out_depth_path = os.path.join(ORGANIZED_DIR, f"{target_material}_3d_verify_depth.jpg")
                    cv2.imwrite(out_depth_path, d_col)
                    print(f"-> Saved: {out_depth_path}")

    print("\nVisual mask verification completed successfully for all materials and liquids.")

if __name__ == "__main__":
    main()
