# Code Review Rules and Requirements Analysis

## Conversation Summary

1. **Code Review Rules Discussion**
   - Reviewed existing code review rules in `.cursor/rules/code_review.mdc`
   - Added new category: Requirements Compliance
   - Discussed how to apply rules in code reviews

2. **RuncHandler Requirements Analysis**
   - Analyzed implementation against engineering requirements
   - Identified missing/incomplete requirements:
     - TARDIS_NETWORKFS_HOST_PATH handling
     - TARDIS_MANAGED_EBS_SIZE_GB for EBS volumes
     - Bind mount validation
     - Current working directory modification

3. **Session Memory Discussion**
   - Clarified session memory limitations
   - Discussed when memory resets
   - Established best practices for maintaining context

## Key Points

1. **Code Review Rules**
   - Structure & Design
   - Code Quality
   - Robustness
   - Performance & Testing
   - Requirements Compliance (new)

2. **Requirements Analysis**
   - Command Processing ✅
   - Container Config ✅
   - Container Files ✅
   - Checkpoint Handler ✅
   - Internal State ✅
   - Error Handling ✅

3. **Session Memory**
   - Maintains context within single conversation
   - Resets on new conversation/refresh
   - Remembers code reviews, requirements, decisions
   - Doesn't remember previous sessions 