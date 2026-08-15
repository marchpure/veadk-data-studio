SKILL_WORKFLOW_RULES = """
*** SKILL DISCOVERY WORKFLOW (MANDATORY) ***

Always check skills first before responding to ANY request that is not a direct, unambiguous database query or dashboard task.
This includes: questions about tools, services, APIs, libraries, workflows, code patterns, usage of named systems or products,
and ANY question where the subject does not clearly match a table or column name in the connected database schemas.
Examples of queries that MUST trigger skill search before dataset exploration:
- "tell me about scribe usage" → could be a skill, repo, or API — not necessarily a database table
- "how does authentication work" → likely a codebase question, check repo skills first
- "what integrations do we have" → check enabled skills catalog
- "explain the deployment pipeline" → check repo skills first

STEP 1: DISCOVER RELEVANT SKILLS (REQUIRED)
1. Call search_enabled_skills(query="<short user intent summary>")
2. Review returned skills and pick the most relevant one(s)

STEP 2: LOAD SKILL DETAILS BEFORE ACTION
1. Call get_skill_definition(skill_name) for selected skill
2. Read source and capabilities carefully:
   - source="byaan", can_execute_api=true  -> API execution is allowed
   - source="custom", can_execute_api=true  -> API execution is allowed (custom skill with API config)
   - source="custom", can_execute_api=false -> informational/instructional only

STEP 3: EXECUTION DECISION
1. If can_execute_api=true (Byaan or API-enabled custom skill):
   - Use execute_skill_api with allowed domain and proper scope
   - For dashboards, save the call using save_skill_query and use returned query_id
2. If Custom skill (can_execute_api=false):
   - Follow its instructions and available tools
   - Never call execute_skill_api for custom skills without API configuration

STEP 4: FALLBACKS
1. If no matching skills are found, continue with normal database/dashboard workflow
2. If no skills are enabled, continue without retry loops
3. Do not repeatedly call search_enabled_skills for the same unchanged request

*** UPDATING CUSTOM SKILLS ***

When user asks to modify, update, add, or remove skill instructions:
1. Call get_skill_definition(skill_name) to retrieve current instructions
2. Make the requested changes (add/remove/modify specific parts as requested)
3. Call update_custom_skill(skill_name, instructions="<complete modified instructions>")
   - Provide the FULL updated instructions, preserving all unchanged parts
   - Only the skill creator can update their own skills
   - Can also update description field if requested and according to what is requested

ABSOLUTE RULES
- Never skip search_enabled_skills for substantive tasks.
- Never execute skill APIs before get_skill_definition.
- Never use execute_skill_api for custom skills without API configuration.
- Never refuse a request as "out of scope" without first calling search_enabled_skills to check for matching skills.
"""
