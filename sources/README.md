# Source files

The build reads these from this folder. They are not in the repository: they are large, they change
often, and the plan documents belong to the plans. Download the current release of each and keep the
file-name patterns.

| File pattern | What | Where |
|---|---|---|
| `partd_2026.zip`, `partd_2027.zip` | Seven text files from the CMS Part D public use file, renamed: `basic_drugs_formulary.txt`, `plan_information.txt`, `beneficiary_cost.txt`, `geographic_locator.txt`, `excluded_drugs_formulary.txt`, `indication_based_coverage.txt`, `insulin_beneficiary_cost.txt` | data.cms.gov: Monthly and Quarterly Prescription Drug Plan Formulary, Pharmacy Network (and Pricing) Information |
| `partd_2026_price_ndc_median.csv` | Columns `ndc, median_unit_cost, mean_unit_cost, plans_reporting`: 30-day unit cost per NDC across plans, from the quarterly pricing file | same quarterly file |
| `CY26 FRF_*.csv`, `CY27 FRF_*.csv` | CMS Formulary Reference Files | cms.gov, Formulary Guidance |
| `section 508 version of * Medicare Part B Payment Limit File*.csv`, `... Drugs Not Payable Under Part B*.csv` | Part B payment limits | cms.gov, ASP Pricing Files |
| `section 508 version of * ASP / AWP / OPPS / PrEP NDC-HCPCS Crosswalk*.csv` | NDC to HCPCS crosswalks | same zip family |
| `MedReimbDrugsFormulary.csv` | NY Medicaid reimbursable drugs (NYRx) | emedny.org, Formulary File |
| `pad-drug-list.pdf` | NYS List of Physician Administered Drugs | emedny.org, PAD search tool |
| `Physician_Manual_Fee_Schedule_Sect3.xls` | NY Medicaid physician drug fee schedule | emedny.org, Physician manual |
| `*Formulary-QHP-EP*.pdf` (one per plan year) | Healthfirst Leaf / Essential Plan comprehensive drug list | healthfirst.org |
| `QHP_Formulary-Document_*.pdf`, `Marketplace_EP_Formulary-Document_*.pdf` | MetroPlus marketplace and Essential Plan formularies | metroplus.org |
| `Prior-Authorization-Medical-Benefit-Grid*.pdf` | Healthfirst medical-benefit PA grid | hfproviders.org |
| `PAD-Auth-Grid_*.pdf` (three) | MetroPlus physician-administered drug authorization grids | metroplus.org |

`build_meta.json` holds the release dates shown in the page. `carry_forward.json` holds a small set of
curated values: names for a few drugs CMS no longer lists, labels for biosimilar codes, and hand-verified
coverage notes.
