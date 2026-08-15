import { useEffect, useCallback } from 'react'
import { useStore } from '@/stores/useStore'
import type { CreateCustomSkillData } from '@/stores/slices/contextSlice'

export function useSlackSkills() {
  const {
    customSkills,
    isLoadingCustomSkills,
    loadCustomSkills,
    createCustomSkill,
    updateCustomSkill,
    deleteCustomSkill,
  } = useStore()

  useEffect(() => {
    loadCustomSkills()
  }, [loadCustomSkills])

  const inboundSkill = customSkills.find(s => s.skill_type === 'slack_inbound')
  const outboundSkill = customSkills.find(s => s.skill_type === 'slack_outbound')

  const createInboundSkill = useCallback(async (data: Omit<CreateCustomSkillData, 'skill_type' | 'scope'>) => {
    if (inboundSkill) throw new Error('Inbound skill already exists')
    return createCustomSkill({ ...data, skill_type: 'slack_inbound', scope: 'org' })
  }, [inboundSkill, createCustomSkill])

  const createOutboundSkill = useCallback(async (data: Omit<CreateCustomSkillData, 'skill_type' | 'scope'>) => {
    if (outboundSkill) throw new Error('Outbound skill already exists')
    return createCustomSkill({ ...data, skill_type: 'slack_outbound', scope: 'org' })
  }, [outboundSkill, createCustomSkill])

  return {
    inboundSkill,
    outboundSkill,
    createInboundSkill,
    createOutboundSkill,
    updateSkill: updateCustomSkill,
    deleteSkill: deleteCustomSkill,
    isLoading: isLoadingCustomSkills,
    refresh: loadCustomSkills,
  }
}
