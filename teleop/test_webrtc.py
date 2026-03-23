import asyncio
import cv2
import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription

async def process_video(track):
    """Reads frames from the video track and displays them using OpenCV."""
    print("Starting video processing...")
    while True:
        try:
            # Await the next frame from the WebRTC track
            frame = await track.recv()
            
            # Convert the PyAV frame to an OpenCV numpy array (BGR format)
            img = frame.to_ndarray(format="bgr24")
            
            # Display the video
            cv2.imshow("WebRTC Video Stream", img)
            
            # Press 'q' to close the window
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        except Exception as e:
            print(f"Track ended or error occurred: {e}")
            break
            
    cv2.destroyAllWindows()

async def run(pc, signaling_url):
    # 1. Add a transceiver to tell the server we want to receive video
    pc.addTransceiver("video", direction="recvonly")

    # 2. Set up the event listener for incoming tracks
    @pc.on("track")
    def on_track(track):
        print(f"Received {track.kind} track")
        if track.kind == "video":
            # Start a background task to process and display the video frames
            asyncio.ensure_future(process_video(track))

    # 3. Create an SDP Offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    # 4. Signaling: Send the offer to the server and wait for the answer
    print(f"Sending offer to server at {signaling_url}...")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            signaling_url,
            json={
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            }
        ) as response:
            if response.status != 200:
                print(f"Signaling failed with status {response.status}")
                return
            answer_data = await response.json()
            
    # 5. Set the remote description (the server's answer)
    answer = RTCSessionDescription(sdp=answer_data["sdp"], type=answer_data["type"])
    await pc.setRemoteDescription(answer)
    print("WebRTC Connection established!")

    # Keep the script alive while the video streams
    await asyncio.sleep(3600)

if __name__ == "__main__":
    # --- CONFIGURATION ---
    # Replace this with the actual signaling endpoint of your WebRTC server
    SIGNALING_URL = "http://192.168.1.232:60001" 
    
    # Initialize the Peer Connection
    pc = RTCPeerConnection()
    
    # Run the asyncio event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run(pc, SIGNALING_URL))
    except KeyboardInterrupt:
        print("Program interrupted by user.")
    finally:
        # Clean up the connection on exit
        loop.run_until_complete(pc.close())