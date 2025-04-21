# ARCH Product Requirements

## Product Overview

ARCH is a container checkpoint-and-restore solution that enables seamless container migration across nodes and time. It allows containers to survive spot instance reclaims, pause during peak hours, and restore without losing progress.

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

## Success Metrics

- **Cost Savings**: Measured reduction in cloud compute costs
- **Resource Utilization**: Improved utilization rates
- **Reliability**: Successful checkpoint/restore operations
- **Performance**: Minimal overhead during normal operation
- **User Adoption**: Number of containers using ARCH

## Implementation Modes

### 1. Basic Mode
- Checkpoint to local path
- User specifies checkpoint image path via environment variable
- ARCH creates subfolder with namespace and container_id for each container
- During checkpoint: image written to subfolder
- During restore: image read from subfolder
- During delete: subfolder deleted on exit code 0

### 2. Network FS Mode
- Support for JuiceFS, EFS, FSx
- User manages filesystem lifecycle (create, mount, unmount, delete)
- ARCH sees network FS as host path
- No performance requirements in initial release

### 3. AWS EBS Mode
- Not supported in initial release
- Planned for future roadmap

## Security & Performance

### Security
- Assumes secure private network or VPN environment
- No additional security measures in initial release
- Access control and encryption planned for future releases

### Performance
- No specific performance requirements for initial release
- Designed for up to 200 concurrent containers per host
- Performance optimizations planned for future releases

## Integration

### Container Orchestration
- ECS & AWS Batch: Task definition integration
- Installation via AMI or userdata
- Other platforms: Plugin architecture for extensibility

### AWS Services
- Initial release: ECS and AWS Batch only
- Future releases: CloudWatch, DynamoDB, managed Grafana

## Limitations

### Container Management
- Container size: Up to 100GB (configurable)
- Checkpoint frequency: One checkpoint per container before termination
- No support for GPU workloads
- No support for container dependencies
- No support for EBS volumes

### State Management
- External database state: Consistent on first restore only
- Multiple restores not supported in initial release

## Development & Support

### Development
- Open-source project from start
- Initial release timeline: Two days (components tested)
- Python-based implementation

### Support
- Comprehensive documentation
- Community support via GitHub
- Enterprise support options planned

## Implementation Priorities

### Phase 1 (Initial Release)
- Local checkpoint/restore
- Network FS support
- Basic monitoring
- Manual checkpoint triggers

### Phase 2 (Future)
- AWS service integration
- Performance improvements
- Extended monitoring
- Automated spot reclaim triggers
- Multiple checkpoints per container
- GPU support
- UI dashboard

## Documentation Requirements

1. User Guides
   - Installation instructions
   - Configuration guide
   - Best practices

2. API Documentation
   - Interface specifications
   - Integration examples
   - Error handling

3. Deployment Guides
   - AWS integration
   - Network FS setup
   - Monitoring setup

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

   - For Spot instances, how will ARCH detect impending instance termination to trigger checkpoints?

See above.

10. **Integration Details**:
    - For AWS Batch integration, will there be specific job definition parameters for ARCH configuration?
    - Nothing in addition to the env variables
    - How will ARCH handle container networking during restore, especially for containers with specific network configurations?
    - Containerd and Runc will be responsible for the network configuration

11. **Operational Considerations**:
    - How will ARCH handle container dependencies (e.g., containers that depend on other containers)?
    - Will not be support in first release
    - What's the strategy for handling container state that exists outside the container (e.g., external databases)?
    - Since there is only one checkpoint before container process terminate, the external database state will be consistent on the first restore. Multiple restore will not be supported for first release.

12. **Development Approach**:
    - Will ARCH be developed as an open-source project from the beginning?
    - Yes
    - What's the expected development timeline for the initial release?
    - Given, all the components have been testest, see code in /src folder, like to release first version on two days

## Conclusion

The product and engineering requirements provide a solid foundation for ARCH, but need refinement to ensure complete alignment. By addressing the gaps and clarifications outlined in this document, we can create a more robust and comprehensive solution that delivers clear value to users while maintaining technical excellence. 