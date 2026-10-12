# Next milestones

1. Verify the new launcher in replay, ground connection, then deliberate flight; confirm shutdown behavior and log diagnostics.
2. Verify a fresh Intel Mac clone and setup; remove unused Gazebo dependencies after solving/testing a smaller environment. Add separate Linux/Apple Silicon environments only when tested.
3. Package ROS nodes, replace JSON control messages with typed interfaces, separate configuration from code and add command validation tests.
4. Audit flight freshness, mode transitions, disarm/landing confirmation and loss-of-input behavior using a fake transport before changing flight logic.
5. Add manual-priority command arbitration. Test automation in replay/mock mode first. Keep hardware execution opt-in.
6. Improve calibration, timestamp handling, map visualization and tracking recovery. Record evidence before claiming map accuracy or metric position.
7. Choose repository license, contribution rules and shared sample data; publish the repository and invite the team.

Suggested ownership: hardware/control; dashboard; SLAM; replay/testing. Use small branches and pull requests; keep the hardware driver as the single command owner.
