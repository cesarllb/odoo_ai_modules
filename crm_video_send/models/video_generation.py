import json
import os
import threading
import time

import requests

# get from the enviroment
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")

hey_gen_config = {
    "background": "#ffffff",
    "avatar_style": "normal",
    "voice_id": "ffb5979428d642abaa9cae60110824e3",
    "avatar_id": "Tyler-incasualsuit-20220721",
    "ratio": "16:9",
}


def request_video(input_text: str):
    url = "https://api.heygen.com/v1/video.generate"
    headers = {"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "application/json"}
    data = {
        "background": hey_gen_config["background"],
        "clips": [
            {
                "avatar_id": hey_gen_config["avatar_id"],
                "avatar_style": hey_gen_config["avatar_style"],
                "input_text": input_text,
                "offset": {"x": 0, "y": 0},
                "scale": 1,
                "voice_id": hey_gen_config["voice_id"],
            }
        ],
        "ratio": "16:9",
        "test": True,
        "version": "v1alpha",
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    return response.json()


def check_if_ready(video_id):
    url = f"https://api.heygen.com/v1/video_status.get?video_id={video_id}"
    headers = {
        "X-Api-Key": HEYGEN_API_KEY,
    }
    response = requests.get(url, headers=headers)
    return response.json()


def get_video_url(input_text, result):
    video_response = request_video(input_text)
    print(video_response)
    try:
        if video_response.get("message") == "Success":
            video_id = video_response["data"]["video_id"]
    except:
        print("Error getting video id")
        return

    while True:
        status_response = check_if_ready(video_id)
        if status_response["data"]["status"] == "completed":
            result["video_url"] = status_response["data"]["video_url"]
            break
        time.sleep(8)


async def get_video_url_thread(input_text: str) -> str:
    result = {}
    thread = threading.Thread(target=get_video_url, args=(input_text, result))
    thread.start()
    thread.join()
    return result.get("video_url") if result else None
