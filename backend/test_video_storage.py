
import asyncio
from uuid import uuid4

from app.storage.video_storage import VideoStorageService


async def main():
    storage = VideoStorageService(
        storage_dir="storage/test_videos"
    )

    task_id = uuid4()
    video_bytes = b"sample-video-content"

    filename = await storage.save(
        video_bytes=video_bytes,
        task_id=task_id,
        extension="mp4",
    )

    file_path = storage.get_file_path(filename)

    assert file_path.exists()
    assert file_path.read_bytes() == video_bytes

    await storage.delete(filename)

    assert not file_path.exists()

    print("Video storage tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
