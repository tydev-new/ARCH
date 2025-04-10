# Tardis Requirements Review

## Overview

This document reviews the product and engineering requirements for Tardis, identifies gaps, and proposes clarifications to ensure alignment between product vision and technical implementation.

## Product Vision Alignment

### Target Users
- **Primary Users**: DevOps engineers and platform teams managing container workloads
- **Secondary Users**: Application developers who need to optimize cloud costs
- **User Personas**:
  - Cloud cost optimizer: Focuses on Spot instance utilization
  - Resource scheduler: Manages workload distribution across on-prem and cloud resources
  - Application developer: Needs simple checkpoint/restore functionality

### Value Proposition
- **Primary Value**: 90% cost reduction with Spot instances
- **Secondary Value**: 30% improvement in resource utilization
- **Tertiary Value**: Simplified container migration and workload management

### Success Metrics
- **Cost Savings**: Measured reduction in cloud compute costs
- **Resource Utilization**: Improved utilization rates
- **Reliability**: Successful checkpoint/restore operations
- **Performance**: Minimal overhead during normal operation
- **User Adoption**: Number of containers using Tardis

## Technical Implementation Gaps

### Implementation Modes
The engineering requirements don't fully address the three implementation modes:

1. **Basic Mode**: Checkpoint to local path
   - Need to clarify file management and cleanup
   - A- The user add environment variable to specify checkpoint image path while starting container, such as docker run, or in AWS Batch job definition. Tardis to create subfolder with namespace and container_id for each container. 
   - During checkpoint, the image is written to subfolder.
   - During restore, the image is read from subfolder
   - During delete, in exit code of 0, the subfolder is deleted.
   
   - Need to specify performance characteristics
   - A- No performance requirement for this version, will be addressed in next roadmap version.

2. **Network FS Mode**: Using network file systems
   - Need to detail integration with JuiceFS, EFS, FSx
   - A- The user is responsible to manager JuiceFS/EFS/FSx lifecycle, such as create, mount, unmount, delete. To Tardis, it'll just appear as a host path.
   
   - Need to specify performance requirements
   - A- No performance requirement for this version, will be addressed in next roadmap version.

3. **AWS EBS Mode**: Using managed EBS volumes
   - Need to detail EBS volume lifecycle management
   - Need to specify AWS-specific requirements and limitations
   - A- Ignore EBS for this version.
   - Both will be addressed in next roadmap version.

### Performance Requirements
- **Checkpoint Time**: Maximum acceptable time for checkpoint operation
- **Restore Time**: Maximum acceptable time for restore operation
- **Overhead**: Maximum acceptable performance impact during normal operation
- A- No performance requirement for this version

- **Scalability**: Maximum number of concurrent containers supported
- A- design for maximum of 200 concurrent containers per host

### Security Considerations
- **Checkpoint Image Security**: Access control and encryption
- **Network FS Security**: Authentication and authorization
- **EBS Volume Security**: Access control and encryption
- A- no security requiremnt, assume Tardis run within the secure private network or VPN

## Clarification Questions and Proposed Answers

### User Experience
**Q**: How should users monitor the checkpoint/restore process?
**A**: 
- A- Should be automated, but user can look into logs for debugging 
- Next rev to integrate logging with AWS CloudWatch
- Next rev to show metrics exposed on AWS DynamoDB and AWS-managed Grafana

### Integration
**Q**: How does Tardis integrate with container orchestration systems?
**A**:
- ECS & AWS Batch: Task definition integration; install Tardis either using built-in AMI or through userdata at each instance startup to pull from Github
- Other platforms: Plugin architecture for extensibility

### Limitations
**Q**: What are the limitations on container size, checkpoint frequency, etc.?
**A**:
- Container size: Up to 100GB (configurable)
- Checkpoint frequency: only one checkpoint, which will kill the container process
- Workload types: Compatible with most Linux containers, no GPU workloads

### Roadmap
**Q**: What features are planned for future releases?
**A**:
- AWS integration
- Multiple checkpoints per container
- GPU support
- UI dashboard for monitoring

### Support
**Q**: What level of support and documentation will be provided?
**A**:
- Comprehensive documentation
- Community support via GitHub
- Enterprise support options

## Implementation Priorities

1. **Phase 1**: Basic functionality
   - Local checkpoint/restore
   - Network FS support
   - Basic monitoring

2. **Phase 2**: Enhanced features
   - AWS integration
   - Improved performance
   - Extended monitoring

## Next Steps

1. **Requirements Refinement**
   - Update engineering requirements to fully address implementation modes
   - Add performance requirements and SLAs
   - Detail AWS EBS volume management

2. **Technical Design**
   - Create detailed architecture diagrams
   - Define interfaces and APIs
   - Specify data flows

3. **Implementation Planning**
   - Break down into manageable tasks
   - Define milestones and deliverables
   - Establish testing strategy

4. **Documentation**
   - Create user guides
   - Develop API documentation
   - Write deployment guides

## Additional Questions for Clarification

8. **Scope Definition**:
   - Is the initial release focused solely on AWS environments, or will it support other cloud providers as well?

Yes, AWS only

   - Will there be any specific AWS service integrations beyond ECS and AWS Batch in the initial release?

No, next release will add CloudWatch, DynamoDB, and managed Grafana


9. **User Workflow**:
   - How will users trigger checkpoints? Is it automatic based on certain conditions, or manual?

Good question.
First version manual trigger.
Will add automated spot reclaim warning trigger in next version.

   - For Spot instances, how will Tardis detect impending instance termination to trigger checkpoints?

See above.

10. **Integration Details**:
    - For AWS Batch integration, will there be specific job definition parameters for Tardis configuration?
    - Nothing in addition to the env variables
    - How will Tardis handle container networking during restore, especially for containers with specific network configurations?
    - Containerd and Runc will be responsible for the network configuration

11. **Operational Considerations**:
    - How will Tardis handle container dependencies (e.g., containers that depend on other containers)?
    - Will not be support in first release
    - What's the strategy for handling container state that exists outside the container (e.g., external databases)?
    - Since there is only one checkpoint before container process terminate, the external database state will be consistent on the first restore. Multiple restore will not be supported for first release.

12. **Development Approach**:
    - Will Tardis be developed as an open-source project from the beginning?
    - Yes
    - What's the expected development timeline for the initial release?
    - Given, all the components have been testest, see code in /src folder, like to release first version on two days

## Conclusion

The product and engineering requirements provide a solid foundation for Tardis, but need refinement to ensure complete alignment. By addressing the gaps and clarifications outlined in this document, we can create a more robust and comprehensive solution that delivers clear value to users while maintaining technical excellence. 