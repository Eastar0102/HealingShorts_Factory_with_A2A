"""
비디오 처리 도구 함수
Veo API 모킹 및 MoviePy를 사용한 seamless loop 생성
"""

import os
import time
import random
import re
from pathlib import Path
from moviepy.editor import VideoFileClip, concatenate_videoclips, ColorClip, CompositeVideoClip
from moviepy.video.fx import speedx
from typing import Optional


def generate_veo_clip(
    prompt: str, 
    output_dir: str = "output",
    duration_seconds: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
    force_mock: bool = False
) -> str:
    """
    Veo API를 사용하여 비디오를 생성합니다.
    
    Args:
        prompt: Veo 프롬프트
        output_dir: 출력 디렉토리
        duration_seconds: 비디오 길이 (초). YouTube Shorts는 15-60초 권장.
        aspect_ratio: 비율 ("16:9" 또는 "9:16"). YouTube Shorts는 "9:16" 권장.
        resolution: 해상도 ("720p" 또는 "1080p"). YouTube Shorts는 "1080p" 권장.
        
    Returns:
        생성된 비디오 파일 경로
    """
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # 출력 디렉토리 생성
    Path(output_dir).mkdir(exist_ok=True)
    
    # Mock 모드 확인
    if force_mock:
        MOCK_MODE = True
        print(f"[Veo] force_mock=True로 인해 MOCK 모드로 실행됩니다.")
    else:
        MOCK_MODE = os.getenv("MOCK_MODE", 'True').lower() == 'true'
    
    if MOCK_MODE:
        # Mock 모드: 더미 비디오 생성 (YouTube Shorts 규격: 1080x1920, 9:16)
        print(f"[Veo] Mock 모드: 프롬프트로 비디오 생성 시뮬레이션: {prompt[:50]}...")
        time.sleep(2)  # API 호출 지연 시뮬레이션
        
        output_path = os.path.join(output_dir, f"veo_generated_{random.randint(1000, 9999)}.mp4")
        
        # Mock 모드에서도 duration_seconds 파라미터 사용
        mock_duration = duration_seconds if duration_seconds else 10
        
        # YouTube Shorts 규격: 1080x1920 (세로형, 9:16 비율)
        clip = ColorClip(
            size=(1080, 1920),  # YouTube Shorts 규격
            color=(random.randint(50, 200), random.randint(50, 200), random.randint(50, 200)),
            duration=mock_duration
        )
        clip.write_videofile(
            output_path,
            fps=30,  # YouTube Shorts 권장 FPS
            codec='libx264',
            audio=False,
            logger=None
        )
        clip.close()
        
        print(f"[Veo] Mock 비디오 생성 완료 (YouTube Shorts 규격): {output_path}")
        return output_path
    
    # 실제 Gemini API Veo 사용
    # 참고: https://ai.google.dev/gemini-api/docs/video?hl=ko&example=dialogue
    try:
        from google import genai
        from google.genai import types
        
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        VEO_MODEL_NAME = os.getenv("VEO_MODEL_NAME", "veo-3.1-generate-preview")
        
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY가 설정되지 않았습니다. "
                ".env 파일에 GEMINI_API_KEY를 설정하거나 MOCK_MODE=True로 설정하세요."
            )
        
        # Gemini API 클라이언트 초기화
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # 프롬프트 정리: "OVERALL PROMPT FOR VEO" 섹션이 있으면 그것만 사용
        cleaned_prompt = prompt
        if "**OVERALL PROMPT FOR VEO:**" in prompt or "OVERALL PROMPT FOR VEO" in prompt:
            # OVERALL PROMPT 섹션 추출
            parts = prompt.split("**OVERALL PROMPT FOR VEO:**")
            if len(parts) > 1:
                cleaned_prompt = parts[-1].strip()
            else:
                # 다른 형식으로 시도
                parts = prompt.split("OVERALL PROMPT FOR VEO")
                if len(parts) > 1:
                    cleaned_prompt = parts[-1].strip()
        
        # 프롬프트에서 불필요한 마크다운 제거 및 정리
        cleaned_prompt = cleaned_prompt.replace("**", "").replace("*", "").strip()
        
        # 프롬프트에 해상도와 길이를 더 명확하게 강조
        # 프롬프트 시작 부분에 기술적 사양을 명확히 추가
        has_resolution = "1080x1920" in cleaned_prompt or "1920x1080" in cleaned_prompt or "vertical" in cleaned_prompt.lower() or "9:16" in cleaned_prompt
        
        if not has_resolution:
            # 해상도가 명시되지 않은 경우 앞부분에 추가
            cleaned_prompt = f"1080x1920 vertical format (9:16 aspect ratio), {cleaned_prompt}"
        else:
            # 해상도가 있지만 시작 부분에 없으면 앞부분에 강조 추가
            if not cleaned_prompt.lower().startswith(("1080x1920", "1920x1080", "vertical", "9:16")):
                # 해상도 정보를 찾아서 앞부분으로 이동
                resolution_match = re.search(r'(1080x1920|1920x1080|vertical.*?9:16|9:16.*?format)', cleaned_prompt, re.IGNORECASE)
                if resolution_match:
                    resolution_text = resolution_match.group(0)
                    cleaned_prompt = cleaned_prompt.replace(resolution_text, "").strip()
                    cleaned_prompt = f"{resolution_text}, {cleaned_prompt}"
                else:
                    cleaned_prompt = f"1080x1920 vertical format (9:16 aspect ratio), {cleaned_prompt}"
        
        # 길이 정보도 확인 및 강조
        has_duration = bool(re.search(r'\d+\s*seconds?', cleaned_prompt, re.IGNORECASE))
        if not has_duration:
            # 길이 정보가 없으면 프롬프트에서 추출 시도 (스토리보드에서)
            duration_match = re.search(r'Duration:\s*(\d+)', prompt, re.IGNORECASE)
            if duration_match:
                duration = duration_match.group(1)
                cleaned_prompt = f"{cleaned_prompt}, Duration: {duration} seconds"
        
        print(f"[Veo] Gemini API Veo 비디오 생성 시작 (모델: {VEO_MODEL_NAME})...")
        print(f"[Veo] 원본 프롬프트 길이: {len(prompt)} 문자")
        print(f"[Veo] 정리된 프롬프트: {cleaned_prompt[:200]}...")
        
        # Veo 비디오 생성 설정 구성
        # 참고: https://ai.google.dev/gemini-api/docs/video?hl=ko&example=dialogue
        from google.genai import types
        
        # 목표 길이에 맞게 필요한 비디오 개수 계산
        # Veo 3.1은 최대 8초까지 생성 가능, 요청당 1개만 생성 가능
        veo_max_duration = 8
        if duration_seconds:
            # 필요한 비디오 개수 계산 (각 8초씩 생성)
            num_videos_needed = max(1, int((duration_seconds / veo_max_duration) + 0.5))  # 반올림
            # 최소 2개 생성하여 다양성 확보 (15초 이상이면 최소 2개)
            if duration_seconds >= 15:
                num_videos_needed = max(2, num_videos_needed)
        else:
            num_videos_needed = 2  # 기본값: 2개
        
        print(f"[Veo] 목표 길이: {duration_seconds}초, 생성할 비디오 개수: {num_videos_needed}개")
        print(f"[Veo] Veo API는 요청당 1개만 생성 가능하므로 {num_videos_needed}번 호출합니다.")
        
        # config 파라미터 구성 (공식 문서 참고)
        config_params = {}
        
        if duration_seconds:
            # Veo 3.1은 4초, 6초, 8초를 지원
            veo_duration = min(int(duration_seconds), veo_max_duration)  # Veo 최대 8초
            config_params["duration_seconds"] = veo_duration
            print(f"[Veo] 각 비디오 길이: {veo_duration}초")
        if aspect_ratio:
            config_params["aspect_ratio"] = aspect_ratio
            print(f"[Veo] 비율 설정: {aspect_ratio}")
        if resolution:
            config_params["resolution"] = resolution
            print(f"[Veo] 해상도 설정: {resolution}")
        
        # GenerateVideosConfig 생성
        video_config = types.GenerateVideosConfig(**config_params) if config_params else None
        print(f"[Veo] Config 파라미터: {config_params}")
        
        # 여러 비디오를 순차적으로 생성 (Veo는 요청당 1개만 생성 가능)
        temp_video_paths = []
        max_wait_time = 600  # 10분
        
        for video_idx in range(num_videos_needed):
            print(f"[Veo] 비디오 {video_idx + 1}/{num_videos_needed} 생성 시작...")
            
            # Veo 비디오 생성 요청 (공식 문서 형식)
            print("[Veo] 비디오 생성 요청 전송 중...")
            if video_config:
                operation = client.models.generate_videos(
                    model=VEO_MODEL_NAME,
                    prompt=cleaned_prompt,
                    config=video_config
                )
            else:
                operation = client.models.generate_videos(
                    model=VEO_MODEL_NAME,
                    prompt=cleaned_prompt,
                )
            
            # 비디오 생성이 완료될 때까지 폴링
            start_time = time.time()
            print(f"[Veo] 비디오 {video_idx + 1} 생성 작업이 시작되었습니다. 완료될 때까지 대기 중...")
            
            while not operation.done:
                elapsed_time = time.time() - start_time
                if elapsed_time > max_wait_time:
                    raise Exception(f"비디오 {video_idx + 1} 생성 시간 초과 (최대 {max_wait_time}초)")
                
                print(f"[Veo] 비디오 {video_idx + 1} 생성 중... (대기 시간: {int(elapsed_time)}초)")
                time.sleep(10)  # 10초마다 상태 확인
                
                # 작업 상태 업데이트
                operation = client.operations.get(operation)
            
            # 작업 완료 후 결과 가져오기
            if not operation.response or not operation.response.generated_videos:
                raise Exception(f"비디오 {video_idx + 1} 생성 응답에 생성된 비디오가 없습니다.")
            
            generated_video = operation.response.generated_videos[0]
            temp_path = os.path.join(output_dir, f"veo_temp_{int(time.time())}_{video_idx}.mp4")
            
            # 비디오 다운로드
            print(f"[Veo] 비디오 {video_idx + 1} 다운로드 중...")
            client.files.download(file=generated_video.video)
            generated_video.video.save(temp_path)
            temp_video_paths.append(temp_path)
            print(f"[Veo] 비디오 {video_idx + 1} 생성 및 다운로드 완료: {temp_path}")
        
        # 여러 비디오를 하나로 합치기
        if len(temp_video_paths) > 1:
            print(f"[Veo] {len(temp_video_paths)}개의 비디오를 하나로 합치는 중...")
            clips = []
            for path in temp_video_paths:
                clip = VideoFileClip(path)
                # 오디오 트랙 확인
                if clip.audio is not None:
                    print(f"[Veo] 비디오에 오디오 트랙이 포함되어 있습니다: {os.path.basename(path)}")
                else:
                    print(f"[Veo] 비디오에 오디오 트랙이 없습니다: {os.path.basename(path)}")
                clips.append(clip)
            
            final_clip = concatenate_videoclips(clips, method="compose")
            
            # 오디오 트랙 확인
            if final_clip.audio is not None:
                print(f"[Veo] 합쳐진 비디오에 오디오 트랙이 포함되어 있습니다.")
            else:
                print(f"[Veo] 경고: 합쳐진 비디오에 오디오 트랙이 없습니다.")
            
            output_path = os.path.join(output_dir, f"veo_generated_{int(time.time())}.mp4")
            final_clip.write_videofile(
                output_path,
                fps=30,
                codec='libx264',
                audio_codec='aac' if final_clip.audio is not None else None,
                audio=True if final_clip.audio is not None else False,
                logger=None
            )
            # 리소스 정리
            final_clip.close()
            for clip in clips:
                clip.close()
            # 임시 파일 삭제
            for temp_path in temp_video_paths:
                try:
                    os.remove(temp_path)
                except:
                    pass
            print(f"[Veo] {len(temp_video_paths)}개의 비디오 합치기 완료: {output_path}")
        else:
            # 비디오가 1개만 생성된 경우
            output_path = temp_video_paths[0]
            # 파일명 변경
            new_path = os.path.join(output_dir, f"veo_generated_{int(time.time())}.mp4")
            os.rename(output_path, new_path)
            output_path = new_path
        
        print(f"[Veo] Gemini API Veo 비디오 생성 완료: {output_path}")
        return output_path
        
    except ImportError as e:
        raise Exception(
            f"google-genai 패키지가 설치되지 않았습니다. "
            f"pip install google-genai를 실행하거나 MOCK_MODE=True로 설정하세요. "
            f"원본 오류: {str(e)}"
        )
    except Exception as e:
        error_str = str(e)
        if "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower() or "429" in error_str:
            # 할당량 초과 시 자동으로 MOCK_MODE로 폴백
            print(f"[Veo] 할당량 초과 감지. MOCK_MODE로 자동 전환합니다...")
            print(f"[Veo] 원본 오류: {error_str}")
            
            # MOCK_MODE로 재시도
            return generate_veo_clip(
                prompt=prompt,
                output_dir=output_dir,
                duration_seconds=duration_seconds,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                force_mock=True  # 강제로 MOCK 모드 사용
            )
        raise Exception(f"Veo 비디오 생성 실패: {error_str}")


def generate_veo_video_for_duration(
    prompt: str,
    output_dir: str = "output",
    total_duration_seconds: Optional[int] = None,
    aspect_ratio: str = "9:16",
    resolution: str = "1080p",
) -> str:
    """
    전체 목표 길이를 기준으로 Veo 비디오를 생성합니다.
    - 8초 이하: 단일 클립 생성
    - 8초 초과: 최대 8초 단위로 여러 클립을 생성한 뒤 순차적으로 이어붙여 하나의 비디오로 반환

    Args:
        prompt: Veo 프롬프트
        output_dir: 출력 디렉토리
        total_duration_seconds: 최종 목표 비디오 길이 (초)
        aspect_ratio: 비율 ("16:9" 또는 "9:16")
        resolution: 해상도 ("720p" 또는 "1080p")

    Returns:
        최종 병합된 비디오 파일 경로
    """
    # total_duration_seconds가 없으면 기존 단일 호출과 동일하게 동작
    if not total_duration_seconds:
        return generate_veo_clip(
            prompt=prompt,
            output_dir=output_dir,
            duration_seconds=None,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )

    # 8초 이하이면 단일 클립만 생성
    if total_duration_seconds <= 8:
        return generate_veo_clip(
            prompt=prompt,
            output_dir=output_dir,
            duration_seconds=int(total_duration_seconds),
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )

    # 8초 초과: [8,8,나머지] 형태로 분할
    remaining = int(total_duration_seconds)
    max_segment = 8
    segments = []
    while remaining > 0:
        seg = min(max_segment, remaining)
        segments.append(seg)
        remaining -= seg

    print(f"[Veo] 전체 길이 {total_duration_seconds}초 요청 → 세그먼트 분할: {segments}")

    # 각 세그먼트 길이에 맞춰 개별 클립 생성
    temp_paths = []
    for idx, seg_duration in enumerate(segments):
        print(f"[Veo] 세그먼트 {idx + 1}/{len(segments)} 생성 (길이: {seg_duration}초)")
        clip_path = generate_veo_clip(
            prompt=prompt,
            output_dir=output_dir,
            duration_seconds=seg_duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        temp_paths.append(clip_path)

    # 세그먼트가 1개면 그대로 반환 (이론상 8초 이하 케이스에서만 발생)
    if len(temp_paths) == 1:
        return temp_paths[0]

    # 여러 클립을 순차적으로 이어붙이기
    print(f"[Veo] {len(temp_paths)}개의 세그먼트를 하나의 비디오로 병합합니다...")
    clips = []
    try:
        for path in temp_paths:
            clip = VideoFileClip(path)
            clips.append(clip)

        final_clip = concatenate_videoclips(clips, method="compose")

        # 최종 출력 경로
        Path(output_dir).mkdir(exist_ok=True)
        output_path = os.path.join(output_dir, f"veo_multi_{int(time.time())}.mp4")

        final_clip.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac" if final_clip.audio is not None else None,
            audio=True if final_clip.audio is not None else False,
            logger=None,
        )

        # 최종 클립도 정리
        final_clip.close()

        print(f"[Veo] 다중 세그먼트 병합 완료: {output_path}")
        return output_path
    finally:
        # 리소스 정리
        for clip in clips:
            try:
                clip.close()
            except Exception as e:
                print(f"[Veo] 클립 리소스 정리 중 오류 (무시): {e}")
        
        # 임시 세그먼트 파일 삭제
        for temp_path in temp_paths:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    print(f"[Veo] 임시 파일 삭제: {os.path.basename(temp_path)}")
            except Exception as e:
                print(f"[Veo] 임시 파일 삭제 실패 (무시): {os.path.basename(temp_path)}, {e}")


def make_seamless_loop(
    input_path: str, 
    output_dir: str = "output",
    target_duration: Optional[float] = None,
    target_resolution: tuple = (1080, 1920)  # YouTube Shorts 규격 (가로, 세로)
) -> str:
    """
    주어진 비디오 파일을 무한 루프가 가능한 형태로 변환합니다.
    마지막 1초를 잘라내어 시작 부분에 추가하고, crossfadein(1.0)을 적용하여 부드럽게 연결합니다.
    YouTube Shorts 규격(1080x1920)에 맞게 리사이즈합니다.
    
    Args:
        input_path: 입력 비디오 파일 경로
        output_dir: 출력 디렉토리
        target_duration: 목표 비디오 길이 (초). None이면 원본 길이 유지. YouTube Shorts는 15-60초 권장.
        target_resolution: 목표 해상도 (가로, 세로). 기본값은 YouTube Shorts 규격 (1080, 1920)
        
    Returns:
        Seamless loop로 변환된 비디오 파일 경로
        
    Raises:
        ValueError: 비디오 길이가 1초 이하인 경우
        FileNotFoundError: 입력 파일이 존재하지 않는 경우
    """
    # 입력 파일 존재 여부 확인
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"입력 비디오 파일을 찾을 수 없습니다: {input_path}")
    
    # 출력 디렉토리 생성
    Path(output_dir).mkdir(exist_ok=True)
    
    # 비디오 클립 로드
    clip = VideoFileClip(input_path)
    original_duration = clip.duration
    original_size = clip.size
    
    # 오디오 트랙 확인
    if clip.audio is not None:
        print(f"[MoviePy] 입력 비디오에 오디오 트랙이 포함되어 있습니다.")
    else:
        print(f"[MoviePy] 입력 비디오에 오디오 트랙이 없습니다.")
    
    # 비디오 길이 검증
    if original_duration <= 1:
        clip.close()
        raise ValueError("비디오 길이가 1초 이하여서 루프를 생성할 수 없습니다.")
    
    try:
        # YouTube Shorts 규격 확인 (Veo에서 이미 정확한 해상도로 생성되므로 리사이즈 불필요)
        target_width, target_height = target_resolution
        if original_size != (target_width, target_height):
            print(f"[MoviePy] 경고: 해상도가 목표와 다릅니다. {original_size} -> {target_resolution}")
            print(f"[MoviePy] Veo에서 이미 정확한 해상도로 생성되어야 하므로 리사이즈를 건너뜁니다.")
        else:
            print(f"[MoviePy] 해상도 확인: {original_size} (정확한 YouTube Shorts 규격)")
        
        # 목표 길이 설정
        if target_duration is not None:
            # YouTube Shorts 최대 길이 제한 확인 (60초)
            # 15초 미만도 허용 (일반 YouTube 비디오로 업로드 가능)
            if target_duration > 60:
                print(f"[MoviePy] 경고: 목표 길이({target_duration}초)가 YouTube Shorts 최대 길이(60초)보다 깁니다. 60초로 조정합니다.")
                target_duration = 60
            
            # 목표 길이에 맞게 클립 조정
            if clip.duration > target_duration:
                # 길면 자르기
                clip = clip.subclip(0, target_duration)
            elif clip.duration < target_duration:
                # 짧으면 확장: 반복 방식 사용 (힐링/ASMR 비디오에 더 자연스러움)
                # 재생 속도를 늦추는 대신 루프로 반복하여 자연스러운 seamless loop 생성
                num_loops = int(target_duration / clip.duration) + 1
                clips_to_concat = [clip] * num_loops
                clip = concatenate_videoclips(clips_to_concat, method="compose")
                clip = clip.subclip(0, target_duration)
                print(f"[MoviePy] 비디오 확장: {original_duration:.2f}초 -> {target_duration}초 (루프 반복 방식)")
                if clip.audio is not None:
                    print(f"[MoviePy] 확장된 비디오에 오디오 트랙이 유지되었습니다.")
        
        duration = clip.duration
        
        # 마지막 1초를 잘라내기
        fade_duration = min(1.0, duration * 0.1)  # 최대 1초, 또는 전체 길이의 10%
        end_clip = clip.subclip(duration - fade_duration, duration)
        
        # 나머지 부분 (처음부터 마지막 fade_duration 전까지)
        main_clip = clip.subclip(0, duration - fade_duration)
        
        # crossfadein을 적용하여 부드러운 전환 생성
        # 마지막 부분에 페이드인 효과 적용
        end_clip = end_clip.crossfadein(fade_duration)
        
        # 클립들을 연결하여 최종 비디오 생성
        # 마지막 부분(페이드인 적용) + 나머지 부분 순서로 연결
        final_clip = concatenate_videoclips([end_clip, main_clip], method="compose")
        
        # 오디오 트랙 확인
        if final_clip.audio is not None:
            print(f"[MoviePy] 최종 비디오에 오디오 트랙이 포함되어 있습니다.")
        else:
            print(f"[MoviePy] 최종 비디오에 오디오 트랙이 없습니다.")
        
        # 출력 파일 경로
        output_filename = f"seamless_loop_{int(time.time())}.mp4"
        output_path = os.path.join(output_dir, output_filename)
        
        # 최종 비디오 길이 저장 (close 전에)
        final_duration = final_clip.duration
        
        # 최종 비디오 저장 (YouTube Shorts 권장 설정)
        final_clip.write_videofile(
            output_path,
            fps=30,  # YouTube Shorts 권장 FPS
            codec='libx264',
            audio_codec='aac' if final_clip.audio is not None else None,
            audio=True if final_clip.audio is not None else False,
            bitrate="8000k",  # YouTube Shorts 권장 비트레이트
            logger=None  # 로그 출력 억제
        )
        
        # 리소스 정리
        final_clip.close()
        main_clip.close()
        end_clip.close()
        clip.close()
        
        print(f"[MoviePy] Seamless loop 생성 완료 (해상도: {target_resolution}, 길이: {final_duration:.2f}초): {output_path}")
        return output_path
        
    except Exception as e:
        # 에러 발생 시 리소스 정리
        clip.close()
        raise Exception(f"Seamless loop 생성 실패: {str(e)}")


def upload_youtube_shorts(
    file_path: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[list] = None,
    privacy_status: str = "public"
) -> str:
    """
    YouTube Shorts에 비디오를 업로드합니다.
    Google 공식 문서를 참고하여 재개 가능한 업로드 및 지수 백오프 재시도 전략을 구현합니다.
    참고: https://developers.google.com/youtube/v3/guides/uploading_a_video
    
    Args:
        file_path: 업로드할 비디오 파일 경로
        title: 비디오 제목
        description: 비디오 설명
        tags: 비디오 태그
        privacy_status: 공개 설정 (public, unlisted, private)
        
    Returns:
        업로드된 YouTube 비디오 URL
    """
    import os
    import random
    import httplib2
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # 파일 존재 여부 확인
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"업로드할 비디오 파일을 찾을 수 없습니다: {file_path}")
    
    # Mock 모드 확인 (가장 먼저 확인)
    MOCK_MODE = os.getenv("MOCK_MODE", "True").lower() == "true"
    
    if MOCK_MODE:
        # Mock 모드: 더미 YouTube URL 반환
        print(f"[YouTube] Mock 모드: 비디오 업로드 시뮬레이션")
        print(f"[YouTube] Mock 모드에서는 실제 YouTube 업로드를 수행하지 않습니다.")
        return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    # 재시도 설정 (공식 문서 참고)
    # httplib2의 기본 재시도를 비활성화하고 직접 재시도 로직 구현
    httplib2.RETRIES = 1
    
    # 최대 재시도 횟수
    MAX_RETRIES = 10
    
    # 재시도 가능한 예외 목록 (공식 문서 참고)
    RETRIABLE_EXCEPTIONS = (
        httplib2.HttpLib2Error,
        IOError,
        OSError,
    )
    
    # 재시도 가능한 HTTP 상태 코드
    RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
    
    # 프로젝트 루트 기준으로 경로 설정
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 환경 변수에서 설정 로드 (MOCK_MODE가 False일 때만)
    YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE")
    YOUTUBE_OAUTH_CREDENTIALS = os.getenv("YOUTUBE_OAUTH_CREDENTIALS")
    
    # 환경 변수 검증 및 자동 탐지
    if YOUTUBE_CLIENT_SECRETS_FILE:
        # 기본값이나 잘못된 경로인 경우 무시
        if (YOUTUBE_CLIENT_SECRETS_FILE.startswith("path/to") or 
            "path/to" in YOUTUBE_CLIENT_SECRETS_FILE or
            not os.path.exists(YOUTUBE_CLIENT_SECRETS_FILE) and not os.path.isabs(YOUTUBE_CLIENT_SECRETS_FILE)):
            # 기본값이 설정된 경우 무시
            print(f"[YouTube] 경고: YOUTUBE_CLIENT_SECRETS_FILE이 기본값이거나 파일이 존재하지 않습니다. 무시하고 자동 탐지를 시도합니다.")
            print(f"[YouTube] 설정된 값: {YOUTUBE_CLIENT_SECRETS_FILE}")
            YOUTUBE_CLIENT_SECRETS_FILE = None
    
    # YOUTUBE_CLIENT_SECRETS_FILE이 설정되지 않은 경우 자동 탐지
    if not YOUTUBE_CLIENT_SECRETS_FILE:
        # 프로젝트 루트에서 client_secrets.json 찾기
        possible_paths = [
            os.path.join(project_root, "client_secrets.json"),
            os.path.join(project_root, "shorts_factory", "client_secrets.json"),
            os.path.join(os.path.dirname(project_root), "client_secrets.json"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                YOUTUBE_CLIENT_SECRETS_FILE = path
                print(f"[YouTube] client_secrets.json 파일을 자동으로 찾았습니다: {path}")
                break
        
        if not YOUTUBE_CLIENT_SECRETS_FILE:
            print(f"[YouTube] 경고: client_secrets.json 파일을 찾을 수 없습니다. 다음 위치에서 탐색했습니다:")
            for path in possible_paths:
                print(f"  - {path}")
    
    # 실제 YouTube Data API를 사용한 비디오 업로드
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        import pickle
        import json
        
        # token.pickle 경로 설정 (이미 project_root는 위에서 설정됨)
        token_pickle_path = os.path.join(project_root, "token.pickle")
        
        # OAuth 2.0 인증 처리
        SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
        credentials = None
        
        # 저장된 credentials 파일 확인
        if os.path.exists(token_pickle_path):
            try:
                with open(token_pickle_path, 'rb') as token:
                    credentials = pickle.load(token)
                print(f"[YouTube] 저장된 인증 정보 로드: {token_pickle_path}")
            except Exception as e:
                print(f"[YouTube] token.pickle 로드 실패: {e}")
                credentials = None
        
        # credentials가 없거나 만료된 경우
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                print("[YouTube] 인증 토큰 만료됨. 갱신 중...")
                try:
                    credentials.refresh(Request())
                    print("[YouTube] 인증 토큰 갱신 완료")
                except Exception as e:
                    print(f"[YouTube] 토큰 갱신 실패: {e}")
                    credentials = None
            else:
                # OAuth 2.0 플로우 시작
                if YOUTUBE_CLIENT_SECRETS_FILE:
                    # 절대 경로로 변환
                    if not os.path.isabs(YOUTUBE_CLIENT_SECRETS_FILE):
                        # 상대 경로인 경우 프로젝트 루트 기준으로 변환
                        secrets_path = os.path.join(project_root, YOUTUBE_CLIENT_SECRETS_FILE)
                    else:
                        secrets_path = YOUTUBE_CLIENT_SECRETS_FILE
                    
                    if os.path.exists(secrets_path):
                        print(f"[YouTube] OAuth 인증 시작: {secrets_path}")
                        flow = InstalledAppFlow.from_client_secrets_file(
                            secrets_path, SCOPES)
                        # BackgroundTask에서는 브라우저 인증이 어려울 수 있으므로 에러 메시지 개선
                        try:
                            credentials = flow.run_local_server(port=0)
                        except Exception as e:
                            raise Exception(
                                f"OAuth 인증 실패: {str(e)}\n\n"
                                f"BackgroundTask에서는 브라우저 인증이 어려울 수 있습니다.\n"
                                f"먼저 서버를 직접 실행하여 한 번 인증한 후 token.pickle 파일이 생성되면 "
                                f"BackgroundTask에서도 사용할 수 있습니다."
                            )
                    else:
                        raise FileNotFoundError(
                            f"client_secrets.json 파일을 찾을 수 없습니다: {secrets_path}\n"
                            f"현재 작업 디렉토리: {os.getcwd()}\n"
                            f"프로젝트 루트: {project_root}"
                        )
                elif YOUTUBE_OAUTH_CREDENTIALS:
                    print("[YouTube] YOUTUBE_OAUTH_CREDENTIALS에서 인증 정보 로드")
                    creds_dict = json.loads(YOUTUBE_OAUTH_CREDENTIALS)
                    credentials = Credentials.from_authorized_user_info(creds_dict, SCOPES)
                else:
                    raise ValueError(
                        "YouTube 업로드를 위해 OAuth 인증이 필요합니다.\n\n"
                        f"설정 방법:\n"
                        f"1. YOUTUBE_CLIENT_SECRETS_FILE=path/to/client_secrets.json 설정\n"
                        f"   또는\n"
                        f"2. YOUTUBE_OAUTH_CREDENTIALS={{\"token\": \"...\", ...}} 설정\n\n"
                        f"현재 설정:\n"
                        f"  YOUTUBE_CLIENT_SECRETS_FILE: {YOUTUBE_CLIENT_SECRETS_FILE}\n"
                        f"  YOUTUBE_OAUTH_CREDENTIALS: {'설정됨' if YOUTUBE_OAUTH_CREDENTIALS else '설정 안 됨'}"
                    )
            
            # credentials 저장
            if credentials:
                try:
                    with open(token_pickle_path, 'wb') as token:
                        pickle.dump(credentials, token)
                    print(f"[YouTube] 인증 정보 저장: {token_pickle_path}")
                except Exception as e:
                    print(f"[YouTube] 인증 정보 저장 실패: {e}")
        
        # YouTube API 클라이언트 생성
        youtube = build('youtube', 'v3', credentials=credentials)
        
        # 기본값 설정
        video_title = title or "Healing Shorts - Auto Generated"
        video_description = description or "Auto-generated healing video for relaxation and ASMR"
        video_tags = tags or ["healing", "asmr", "relaxing", "meditation"]
        video_privacy = privacy_status or "unlisted"
        
        # 업로드 요청 본문
        body = {
            'snippet': {
                'title': video_title,
                'description': video_description,
                'tags': video_tags,
                'categoryId': '10'  # Music 카테고리
            },
            'status': {
                'privacyStatus': video_privacy
            }
        }
        
        # 미디어 파일 업로드 객체 생성 (공식 문서 참고)
        # chunksize=-1: 전체 파일을 한 번에 업로드 (재시도 시 중단된 지점부터 재개)
        # resumable=True: 재개 가능한 업로드 활성화
        media = MediaFileUpload(
            file_path,
            chunksize=-1,
            resumable=True,
            mimetype='video/*'
        )
        
        # 비디오 업로드 요청
        print(f"[YouTube] 비디오 업로드 시작: {file_path}")
        insert_request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        
        # 재개 가능한 업로드 실행 (공식 문서의 resumable_upload 함수 방식)
        return resumable_upload(insert_request, file_path, MAX_RETRIES, RETRIABLE_EXCEPTIONS, RETRIABLE_STATUS_CODES)
            
    except ImportError as e:
        raise Exception(
            f"YouTube 업로드를 위한 패키지가 설치되지 않았습니다.\n"
            f"pip install google-api-python-client google-auth-oauthlib google-auth-httplib2를 실행하세요.\n"
            f"원본 오류: {str(e)}"
        )
    except Exception as e:
        error_str = str(e)
        print(f"[YouTube] 업로드 오류: {error_str}")
        
        # MOCK_MODE가 True인 경우 더 친절한 메시지와 함께 Mock URL 반환
        current_mock_mode = os.getenv("MOCK_MODE", "True").lower() == "true"
        if current_mock_mode:
            print(f"[YouTube] MOCK_MODE=True이므로 실제 업로드는 수행되지 않습니다. Mock URL을 반환합니다.")
            return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        
        raise Exception(f"YouTube 업로드 실패: {error_str}")


def resumable_upload(insert_request, file_path: str, MAX_RETRIES: int, RETRIABLE_EXCEPTIONS: tuple, RETRIABLE_STATUS_CODES: list) -> str:
    """
    재개 가능한 업로드를 실행합니다 (공식 문서의 resumable_upload 함수 구현).
    지수 백오프 전략을 사용하여 실패한 업로드를 재시도합니다.
    
    참고: https://developers.google.com/youtube/v3/guides/uploading_a_video
    
    Args:
        insert_request: YouTube API의 videos().insert() 요청 객체
        file_path: 업로드할 비디오 파일 경로 (진행률 계산용)
        MAX_RETRIES: 최대 재시도 횟수
        RETRIABLE_EXCEPTIONS: 재시도 가능한 예외 튜플
        RETRIABLE_STATUS_CODES: 재시도 가능한 HTTP 상태 코드 리스트
        
    Returns:
        업로드된 YouTube 비디오 URL
    """
    import os
    import random
    import time
    from googleapiclient.errors import HttpError
    
    response = None
    error = None
    retry = 0
    
    while response is None:
        try:
            print(f"[YouTube] 업로드 중... (재시도: {retry})")
            status, response = insert_request.next_chunk()
            
            if status:
                # 업로드 진행률 표시 (공식 문서 참고)
                if hasattr(status, 'progress'):
                    progress = int(status.progress() * 100)
                    print(f"[YouTube] 업로드 진행률: {progress}%")
                elif hasattr(status, 'resumable_progress'):
                    # 재개 가능한 업로드의 경우
                    uploaded_bytes = status.resumable_progress
                    file_size = os.path.getsize(file_path)
                    progress = int((uploaded_bytes / file_size) * 100) if file_size > 0 else 0
                    print(f"[YouTube] 업로드 진행률: {progress}% ({uploaded_bytes}/{file_size} bytes)")
            
            if response is not None:
                if 'id' in response:
                    video_id = response['id']
                    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                    print(f"[YouTube] ✅ 업로드 완료: {youtube_url}")
                    return youtube_url
                else:
                    raise Exception(f"업로드 응답에 비디오 ID가 없습니다: {response}")
                    
        except HttpError as e:
            # HttpError인 경우 상태 코드 확인 (공식 문서 참고)
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = f"재시도 가능한 HTTP 오류 {e.resp.status} 발생: {str(e)}"
            else:
                # 재시도 불가능한 HTTP 오류는 즉시 예외 발생
                print(f"[YouTube] 재시도 불가능한 HTTP 오류 {e.resp.status}: {str(e)}")
                raise
        except RETRIABLE_EXCEPTIONS as e:
            # 재시도 가능한 예외 (공식 문서 참고)
            error = f"재시도 가능한 오류 발생: {str(e)}"
        except Exception as e:
            # 재시도 불가능한 기타 예외는 즉시 예외 발생
            print(f"[YouTube] 재시도 불가능한 오류: {str(e)}")
            raise
        
        # 오류가 발생한 경우 재시도 로직 실행 (공식 문서의 지수 백오프 전략)
        if error is not None:
            print(f"[YouTube] {error}")
            retry += 1
            if retry > MAX_RETRIES:
                raise Exception(f"업로드 재시도 실패 ({MAX_RETRIES}회 시도): {error}")
            
            # 지수 백오프 전략 (공식 문서 참고)
            max_sleep = 2 ** retry
            sleep_seconds = random.random() * max_sleep
            print(f"[YouTube] {sleep_seconds:.2f}초 후 재시도... ({retry}/{MAX_RETRIES})")
            time.sleep(sleep_seconds)
            error = None  # 재시도 전 오류 초기화

