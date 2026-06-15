def get_hardcoded_sections():
    """Fallback hardcoded sections if JSON file not present."""
    return [
        {
            'section_number': 'Section 2(f)',
            'title': 'Definition of Information',
            'module': 'Foundational Definitions',
            'definition': 'Information means any material in any form including records, documents, memos, e-mails, opinions, advices, press releases, circulars, orders, logbooks, contracts, reports, papers, samples, models, data material held in any electronic form.',
            'practical_implication': 'RTI only covers EXISTING information. PIO is not required to create, compile, or provide opinions. If the information does not exist in record form, the RTI cannot be fulfilled.',
            'chips_relevance': 'CHiPS must only provide information that exists in its records. Requests for analysis, reports, or opinions not already documented can be declined.',
            'common_mistakes': 'PIOs sometimes try to answer opinion-seeking RTIs. This is not required under the Act.',
            'source_reference': 'RTI Act 2005, Section 2(f); CG RTI Rules 2005',
            'keywords': ['definition', 'information', 'email', 'record', 'opinion', 'advice']
        },
        {
            'section_number': 'Section 4',
            'title': 'Proactive Disclosure',
            'module': 'Disclosure Obligations',
            'definition': 'Every public authority shall maintain all its records duly catalogued and publish within 120 days of the Act coming into force 17 categories of information including organization details, powers and duties, rules and regulations, and annual reports.',
            'practical_implication': 'Proactively disclosed information reduces RTI burden. If information is on CHiPS website, direct applicants there.',
            'chips_relevance': 'CHiPS should maintain updated Section 4 disclosures on cg.gov.in/chips. This reduces RTI load significantly.',
            'common_mistakes': 'Not updating proactive disclosures regularly, forcing users to submit RTIs for public docs.',
            'source_reference': 'RTI Act 2005, Section 4(1)(b)',
            'keywords': ['proactive', 'disclosure', 'website', 'publication', 'obligations']
        },
        {
            'section_number': 'Section 6(3)',
            'title': 'Transfer of RTI Application',
            'module': 'Transfer Rules',
            'definition': 'Where an application is made to a public authority for information which is held by another public authority, the PIO shall transfer the application or part thereof to the other public authority within 5 days and inform the applicant.',
            'practical_implication': 'Transfer must happen within 5 days. The applicant must be informed. The transferred authority then has 30 days to respond (not 30 minus the days already spent).',
            'chips_relevance': 'Most non-IT RTIs received by CHiPS should be transferred under Section 6(3) to the relevant department.',
            'common_mistakes': 'Transferring without informing applicant. Counting transfer days as part of the 30-day window incorrectly.',
            'source_reference': 'RTI Act 2005, Section 6(3)',
            'keywords': ['transfer', 'jurisdiction', '5 days', 'other department', 'wrong department']
        },
        {
            'section_number': 'Section 7',
            'title': 'Disposal of Request — Timelines and Fees',
            'module': 'Response Timelines',
            'definition': 'PIO shall provide information within 30 days of receipt of request. For life and liberty matters: 48 hours. If referred to third party under Section 11: 40 days. Fee: Rs. 2 per page (A4/A3), Rs. 50 for diskette/floppy.',
            'practical_implication': 'The 30-day clock starts from the day after receipt. Fees must be communicated with the rejection/approval notice. Free information for BPL applicants.',
            'chips_relevance': 'CHiPS digital records may have no per-page cost if provided electronically. Clarify fee structure in response.',
            'common_mistakes': 'Delaying beyond 30 days without notifying fees. Failure to supply info free of charge if 30 days pass.',
            'source_reference': 'RTI Act 2005, Section 7(1), Section 7(5)',
            'keywords': ['timeline', '30 days', '48 hours', 'life', 'liberty', 'fee', 'page cost', 'payment']
        },
        {
            'section_number': 'Section 8(1)',
            'title': 'Exemptions from Disclosure',
            'module': 'Exemption Framework',
            'definition': 'Information exempt from disclosure includes: (a) national security, (d) commercial confidence/trade secrets, (e) fiduciary relationship, (g) informant identity/witness, (h) ongoing investigation, (j) personal privacy.',
            'practical_implication': 'Exemptions are NOT absolute. Section 8(2) overrides exemptions where corruption or human rights violations are alleged. Every exemption requires specific reasoning — generic rejection is illegal.',
            'chips_relevance': 'CHiPS exemptions most commonly applicable: 8(1)(d) for vendor contracts, 8(1)(e) for third-party data shared in confidence.',
            'common_mistakes': 'Applying 8(1)(j) to everything. Not checking Section 8(2) before applying exemption.',
            'source_reference': 'RTI Act 2005, Section 8(1)(a)–(j)',
            'keywords': ['exemption', 'security', 'fiduciary', 'investigation', 'refusal', 'withhold']
        },
        {
            'section_number': 'Section 8(1)(j)',
            'title': 'Personal Information Exemption',
            'module': 'Exemption Framework',
            'definition': 'Information which relates to personal information, the disclosure of which has no relationship to any public activity or interest, or which would cause unwarranted invasion of the privacy of the individual.',
            'practical_implication': 'This exemption has TWO conditions: (1) no public interest relationship AND (2) would invade privacy. Both must be true. Public officials acting in official capacity are NOT covered by this exemption.',
            'chips_relevance': 'Employee personal details (salary, home address, family) are covered. But employee official conduct, project assignments, and official decisions are NOT covered.',
            'common_mistakes': 'Using 8(1)(j) to protect all employee information including official acts.',
            'source_reference': 'RTI Act 2005, Section 8(1)(j); CIC Order No. CIC/SA/A/2012/000011',
            'keywords': ['personal', 'privacy', 'salary', 'address', 'medical', 'favourite', 'employee']
        },
        {
            'section_number': 'Section 11',
            'title': 'Third Party Information Procedure',
            'module': 'Third Party Rights',
            'definition': 'Where information relates to or has been supplied by a third party and the third party has treated it as confidential, the PIO shall give notice to the third party and allow them to make representation within 10 days before deciding on disclosure.',
            'practical_implication': 'MANDATORY procedure — cannot be skipped. Third party gets 10 days to respond. PIO then has 40 days total (not 30) to give final decision. Failure to follow Section 11 = procedural violation.',
            'chips_relevance': 'Any RTI about vendor contracts, third-party software, or data provided by companies to CHiPS in confidence must go through Section 11 procedure.',
            'common_mistakes': 'Disclosing third-party commercial data without Section 11 notice. This is a serious violation.',
            'source_reference': 'RTI Act 2005, Section 11(1)',
            'keywords': ['third party', 'confidential', 'vendor', 'contract', 'representation', '10 days']
        },
        {
            'section_number': 'CG Rule 4',
            'title': '150-Word Application Limit',
            'module': 'Chhattisgarh RTI Rules',
            'definition': 'Under Chhattisgarh RTI Rules, an RTI request shall ordinarily relate to one subject matter and should not exceed 150 words. Applications exceeding this may be returned for resubmission.',
            'practical_implication': 'If the application exceeds 150 words or asks about multiple unrelated subjects, PIO may return it and ask for resubmission as separate applications.',
            'chips_relevance': 'CHiPS PIO should check word count and subject unity before processing. Multi-subject RTIs should be bifurcated into separate applications.',
            'common_mistakes': 'Rejecting applications outright based on word limit instead of asking for resubmission.',
            'source_reference': 'CG RTI Rules 2005, Rule 4',
            'keywords': ['chhattisgarh', 'rules', 'word limit', '150 words', 'resubmission', 'subject']
        }
    ]
