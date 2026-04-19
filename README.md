## Google Physical AI Hackathon — Project README

🧠 Project Title
EcoSort AI Agent Autonomous, Edge-Powered Waste Sorting for Kerala. Mainly 

Key Elements In the Project

- SO100 & SO101 Open Souce Leader and Follower Robot Arm (Base on ST)
- 

Segmentation Model Training Methodology 

1. Dataset was collected according to local setting using the camera
2. The images are uploaded in the roboflow platform for annoation and training 
3. The annotation is done based on the number of desire classed for the waste classification that is mainly 4. categories and the part of the robotic arm for better localization in the image frame
5. Once the image is annotated they can be trained using the Yolo26 segmentation model using pytorch which is a frontier model for object detection and classification as of April 2026 and is suitable to be run in edge hardware
6. The trained model produces at `best.pt` file which needs to be converted to a compiled format to be run in edge 
7. This model is then required to be converted to the Hailo executable format .hef which is process of quantization that is done with the help of Hailo Data Flow Compiler and Hailo Runtime 
8. Once converted this can be deployed locally 