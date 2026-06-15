const DEPARTMENT_NAMES: Record<string, string> = {
  chips: 'CHiPS (Chhattisgarh Infotech Promotion Society)',
  wcd: 'Women & Child Development Department',
  revenue: 'Revenue Department',
  pwd: 'Public Works Department',
  health: 'Health & Family Welfare Department',
  finance: 'Finance Department',
  cooperation: 'Cooperation Department',
  labour: 'Labour Department',
  law_legislative: 'Law & Legislative Affairs Department',
  school_education: 'School Education Department',
  social_welfare: 'Social Welfare Department',
}

export function displayDepartmentName(primaryDepartment?: string, departmentName?: string): string {
  const explicitName = (departmentName || '').trim()
  if (explicitName && explicitName.toLowerCase() !== 'unknown') return explicitName

  const raw = (primaryDepartment || '').trim()
  if (!raw) return 'N/A'

  const key = raw.toLowerCase()
  if (DEPARTMENT_NAMES[key]) return DEPARTMENT_NAMES[key]

  return raw
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ')
}
