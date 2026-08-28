/**
 * Legal Metrology Inspection System - Client Application Layer (Phase 6 Final MVP)
 * Connects all 13 Stitch UI templates to the FastAPI backend seamlessly.
 */

const App = {
    API_BASE: window.location.origin,

    // ----------------- Auth State Helpers -----------------
    getToken() {
        return localStorage.getItem('auth_token');
    },

    setToken(token) {
        localStorage.setItem('auth_token', token);
    },

    getProfile() {
        try {
            return JSON.parse(localStorage.getItem('officer_profile') || '{}');
        } catch {
            return {};
        }
    },

    setProfile(profile) {
        localStorage.setItem('officer_profile', JSON.stringify(profile));
    },

    logout() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('officer_profile');
        sessionStorage.clear();
        window.location.href = '/stitch/code/01_login.html';
    },

    requireAuth() {
        const token = this.getToken();
        if (!token) {
            window.location.href = '/stitch/code/01_login.html';
            return false;
        }
        return true;
    },

    async fetchAuth(endpoint, options = {}) {
        const token = this.getToken();
        const headers = {
            ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...(options.headers || {})
        };

        const response = await fetch(`${this.API_BASE}${endpoint}`, {
            ...options,
            headers
        });

        if (response.status === 401) {
            this.logout();
            throw new Error('Session expired. Please sign in again.');
        }

        return response;
    },

    // ----------------- Screen Router Initializer -----------------

    init() {
        const path = window.location.pathname;

        if (path.includes('01_login.html')) {
            this.initLogin();
        } else if (path.includes('02_dashboard.html')) {
            this.initDashboard();
        } else if (path.includes('04_new_inspection_step1.html')) {
            this.initNewInspection();
        } else if (path.includes('09_capture_images_warning.html')) {
            this.initCaptureImages();
        } else if (path.includes('12_analyzing.html')) {
            this.initAnalyzing();
        } else if (path.includes('03_extracted_declarations.html')) {
            this.initExtractedDeclarations();
        } else if (path.includes('05_findings.html')) {
            this.initFindings();
        } else if (path.includes('06_evidence_review.html')) {
            this.initEvidenceReview();
        } else if (path.includes('13_step3_review_and_submit.html')) {
            this.initReviewAndSubmit();
        } else if (path.includes('07_inspection_report_preview.html')) {
            this.initReportPreview();
        } else if (path.includes('08_reports_list.html')) {
            this.initReportsList();
        } else if (path.includes('10_profile.html')) {
            this.initProfile();
        } else {
            this.requireAuth();
            this.initCommonNav();
        }
    },

    // 1. Login Controller
    initLogin() {
        if (this.getToken()) {
            window.location.href = '/stitch/code/02_dashboard.html';
            return;
        }

        const form = document.querySelector('form');
        const inspectorIdInput = document.getElementById('inspector-id');
        const passwordInput = document.getElementById('password');
        const errorMessage = document.getElementById('error-message');
        const submitBtn = form ? form.querySelector('button[type="submit"]') : null;

        if (inspectorIdInput && !inspectorIdInput.value) {
            inspectorIdInput.value = 'DOCA-INSP-842';
        }
        if (passwordInput && !passwordInput.value) {
            passwordInput.value = 'admin123';
        }

        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                if (errorMessage) errorMessage.classList.add('hidden');
                
                const officer_id = inspectorIdInput.value.trim();
                const password = passwordInput.value;

                if (!officer_id || !password) return;

                if (submitBtn) {
                    submitBtn.disabled = true;
                    const textSpan = submitBtn.querySelector('.button-text');
                    const spinner = submitBtn.querySelector('.loading-spinner');
                    if (textSpan) textSpan.classList.add('hidden');
                    if (spinner) spinner.classList.remove('hidden');
                }

                try {
                    const res = await fetch(`${this.API_BASE}/api/auth/login`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ officer_id, password })
                    });

                    const data = await res.json();

                    if (!res.ok) {
                        throw new Error(data.detail || 'Authentication failed');
                    }

                    this.setToken(data.access_token);
                    this.setProfile({
                        officer_id: data.officer_id,
                        full_name: data.full_name,
                        designation: data.designation,
                        zone: data.zone
                    });

                    window.location.href = '/stitch/code/02_dashboard.html';
                } catch (err) {
                    if (errorMessage) {
                        errorMessage.querySelector('span:last-child').textContent = err.message;
                        errorMessage.classList.remove('hidden');
                    }
                } finally {
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        const textSpan = submitBtn.querySelector('.button-text');
                        const spinner = submitBtn.querySelector('.loading-spinner');
                        if (textSpan) textSpan.classList.remove('hidden');
                        if (spinner) spinner.classList.add('hidden');
                    }
                }
            });
        }
    },

    // 2. Dashboard Controller
    async initDashboard() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        const profile = this.getProfile();
        
        const welcomeH1 = document.querySelector('main h1');
        if (welcomeH1 && profile.full_name) {
            welcomeH1.textContent = `Good morning, ${profile.full_name}`;
        }
        
        const welcomeP = document.querySelector('main div > p.text-on-surface-variant');
        if (welcomeP && profile.officer_id) {
            const today = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
            welcomeP.textContent = `ID: ${profile.officer_id} • ${today}`;
        }

        try {
            const res = await this.fetchAuth('/api/dashboard');
            if (res.ok) {
                const data = await res.json();
                this.renderDashboardMetrics(data);
                this.renderRecentInspections(data.recent_inspections);
            }
        } catch (err) {
            console.error('Failed to load dashboard stats:', err);
        }
    },

    renderDashboardMetrics(data) {
        const metricCards = document.querySelectorAll('div.grid.grid-cols-2 > div, div.grid.grid-cols-2.md\\:grid-cols-4 > div');
        if (metricCards.length >= 4) {
            const totalSpan = metricCards[0].querySelector('span.font-headline-lg');
            if (totalSpan) totalSpan.textContent = String(data.total_inspections).padStart(2, '0');

            const verifySpan = metricCards[1].querySelector('span.font-headline-lg');
            if (verifySpan) verifySpan.textContent = String(data.needs_manual_verification).padStart(2, '0');

            const verifiedSpan = metricCards[2].querySelector('span.font-headline-lg');
            if (verifiedSpan) verifiedSpan.textContent = String(data.verified_inspections).padStart(2, '0');

            const nonCompSpan = metricCards[3].querySelector('span.font-headline-lg');
            if (nonCompSpan) nonCompSpan.textContent = String(data.potential_non_compliance).padStart(2, '0');
        }
    },

    renderRecentInspections(inspections) {
        const container = document.querySelector('main div.flex.flex-col.border.border-border-subtle.rounded');
        if (!container) return;

        const header = container.querySelector('.bg-surface-container-low');
        container.innerHTML = '';
        if (header) container.appendChild(header);

        if (!inspections || inspections.length === 0) {
            const emptyRow = document.createElement('div');
            emptyRow.className = 'p-6 text-center text-sm text-on-surface-variant';
            emptyRow.textContent = 'No inspections recorded yet. Click "+ NEW INSPECTION" to begin.';
            container.appendChild(emptyRow);
            return;
        }

        inspections.forEach((insp, idx) => {
            const row = document.createElement('div');
            row.className = `grid grid-cols-1 md:grid-cols-12 gap-tight md:gap-base px-stack-sm py-stack-sm ${idx < inspections.length - 1 ? 'border-b border-border-subtle' : ''} hover:bg-[#eff4ff] cursor-pointer transition-colors`;
            
            let statusBadge = '<span class="font-caption text-caption bg-slate-100 text-slate-700 px-2 py-0.5 rounded border border-slate-300">Draft</span>';
            if (insp.overall_status === 'POTENTIAL_NON_COMPLIANCE') {
                statusBadge = '<span class="font-caption text-caption bg-status-red-bg text-status-red-text px-2 py-0.5 rounded border border-status-red-text">Potential Non-Compliance</span>';
            } else if (insp.overall_status === 'NO_POTENTIAL_VIOLATIONS' || insp.overall_status === 'VERIFIED_COMPLIANT') {
                statusBadge = '<span class="font-caption text-caption bg-status-green-bg text-status-green-text px-2 py-0.5 rounded border border-status-green-text">Verified Compliant</span>';
            } else if (insp.overall_status === 'NEEDS_MANUAL_VERIFICATION') {
                statusBadge = '<span class="font-caption text-caption bg-status-amber-bg text-status-amber-text px-2 py-0.5 rounded border border-status-amber-text">Needs Manual Verification</span>';
            }

            row.innerHTML = `
                <div class="col-span-2 font-body-sm text-body-sm text-on-surface-variant font-mono">${insp.inspection_number}</div>
                <div class="col-span-4 font-body-md text-body-md text-on-surface font-medium">${insp.product_name}</div>
                <div class="col-span-3 font-body-sm text-body-sm text-on-surface-variant">${insp.location}</div>
                <div class="col-span-3 flex items-center">${statusBadge}</div>
            `;

            row.addEventListener('click', () => {
                sessionStorage.setItem('active_inspection_id', insp.id);
                window.location.href = '/stitch/code/05_findings.html';
            });

            container.appendChild(row);
        });
    },

    // 3. New Inspection Step 1 Controller
    initNewInspection() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        const profile = this.getProfile();
        const form = document.querySelector('form');
        
        let idInput, dateInput, officerInput, productNameInput, brandInput, categorySelect, locationInput, batchInput, mfgInput, notesInput;
        
        const allInputs = document.querySelectorAll('input[type="text"], select, textarea');
        allInputs.forEach(input => {
            const label = input.previousElementSibling?.textContent || '';
            if (label.includes('Inspection ID')) idInput = input;
            else if (label.includes('Date & Time')) dateInput = input;
            else if (label.includes('Inspector ID')) officerInput = input;
            else if (label.includes('Product Name')) productNameInput = input;
            else if (label.includes('Brand')) brandInput = input;
            else if (label.includes('Category')) categorySelect = input;
            else if (label.includes('Location')) locationInput = input;
            else if (label.includes('Batch')) batchInput = input;
            else if (label.includes('Manufacturer')) mfgInput = input;
            else if (label.includes('Notes')) notesInput = input;
        });

        if (officerInput && profile.full_name) {
            officerInput.value = `${profile.full_name} (${profile.officer_id})`;
        }
        if (dateInput) {
            dateInput.value = new Date().toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
        }
        if (idInput) {
            idInput.value = 'Auto-generated on save';
        }
        if (locationInput) {
            locationInput.removeAttribute('readonly');
            if (!locationInput.value || locationInput.value === 'Sector 4 Market') {
                locationInput.value = profile.zone || 'Central Delhi Retail Market';
            }
        }

        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();

                const product_name = productNameInput ? productNameInput.value.trim() : '';
                const brand_name = brandInput ? brandInput.value.trim() : '';
                const category = categorySelect ? categorySelect.value : 'Packaged Food';
                const location = locationInput ? locationInput.value.trim() : (profile.zone || 'Field Inspection Site');
                const batch_number = batchInput ? batchInput.value.trim() : '';
                const notes = notesInput ? notesInput.value.trim() : '';

                if (!product_name) {
                    alert('Please enter a product name');
                    return;
                }

                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.textContent = 'Saving Inspection...';
                }

                try {
                    const res = await this.fetchAuth('/api/inspections', {
                        method: 'POST',
                        body: JSON.stringify({
                            product_name,
                            brand_name,
                            category,
                            location,
                            batch_number,
                            notes
                        })
                    });

                    if (!res.ok) {
                        const errData = await res.json();
                        throw new Error(errData.detail || 'Failed to create inspection');
                    }

                    const inspection = await res.json();
                    sessionStorage.setItem('active_inspection_id', inspection.id);
                    sessionStorage.setItem('active_inspection_number', inspection.inspection_number);

                    window.location.href = '/stitch/code/09_capture_images_warning.html';
                } catch (err) {
                    alert(`Error: ${err.message}`);
                } finally {
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.textContent = 'Continue';
                    }
                }
            });
        }
    },

    // 4. Image Upload Controller
    async initCaptureImages() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        let inspectionId = sessionStorage.getItem('active_inspection_id');
        if (!inspectionId) {
            try {
                const recentsRes = await this.fetchAuth('/api/inspections/recent');
                if (recentsRes.ok) {
                    const recents = await recentsRes.json();
                    if (recents.length > 0) {
                        inspectionId = recents[0].id;
                        sessionStorage.setItem('active_inspection_id', inspectionId);
                    }
                }
            } catch (err) {
                console.error(err);
            }
        }

        if (!inspectionId) {
            window.location.href = '/stitch/code/04_new_inspection_step1.html';
            return;
        }

        let fileInput = document.getElementById('global-file-input');
        if (!fileInput) {
            fileInput = document.createElement('input');
            fileInput.type = 'file';
            fileInput.id = 'global-file-input';
            fileInput.accept = 'image/jpeg,image/png,image/webp';
            fileInput.className = 'hidden';
            document.body.appendChild(fileInput);
        }

        let currentUploadViewType = 'front';

        const loadImages = async () => {
            try {
                const res = await this.fetchAuth(`/api/inspections/${inspectionId}/images`);
                if (res.ok) {
                    const images = await res.json();
                    this.renderImageSlots(images, inspectionId);
                }
            } catch (err) {
                console.error('Failed to load images:', err);
            }
        };

        await loadImages();

        this.bindUploadSlots((viewType) => {
            currentUploadViewType = viewType;
            fileInput.click();
        });

        fileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);
            formData.append('view_type', currentUploadViewType);

            try {
                const res = await this.fetchAuth(`/api/inspections/${inspectionId}/images`, {
                    method: 'POST',
                    body: formData
                });
                if (!res.ok) {
                    const errData = await res.json();
                    throw new Error(errData.detail || 'Image upload failed');
                }
                await loadImages();
            } catch (err) {
                alert(`Upload failed: ${err.message}`);
            } finally {
                fileInput.value = '';
            }
        });

        const continueBtn = document.querySelector('button.bg-\\[\\#E8590C\\], button:has([data-icon="warning"])');
        if (continueBtn) {
            continueBtn.addEventListener('click', (e) => {
                e.preventDefault();
                window.location.href = '/stitch/code/12_analyzing.html';
            });
        }
    },

    bindUploadSlots(onUploadRequest) {
        const slotsContainer = document.querySelector('main > div.flex.flex-col.gap-stack-md');
        if (!slotsContainer) return;

        const slotCards = slotsContainer.querySelectorAll(':scope > div');
        slotCards.forEach(card => {
            const labelEl = card.querySelector('span.font-label-caps');
            const viewType = labelEl ? labelEl.textContent.trim().toLowerCase() : 'front';

            const emptyAddBox = card.querySelector('[data-icon="add_a_photo"]')?.closest('div.flex-col');
            const retakeBtn = Array.from(card.querySelectorAll('button')).find(b => b.textContent.includes('Retake'));

            if (emptyAddBox) {
                emptyAddBox.style.cursor = 'pointer';
                emptyAddBox.onclick = () => onUploadRequest(viewType);
            }
            if (retakeBtn) {
                retakeBtn.onclick = () => onUploadRequest(viewType);
            }
        });
    },

    renderImageSlots(images, inspectionId) {
        const slotsContainer = document.querySelector('main > div.flex.flex-col.gap-stack-md');
        if (!slotsContainer) return;

        const slotCards = slotsContainer.querySelectorAll(':scope > div');
        const viewMap = {
            front: images.find(img => img.view_type === 'front'),
            back: images.find(img => img.view_type === 'back'),
            side: images.find(img => img.view_type === 'side' || img.view_type === 'panel')
        };

        slotCards.forEach(card => {
            const labelEl = card.querySelector('span.font-label-caps');
            const viewType = labelEl ? labelEl.textContent.trim().toLowerCase() : 'front';
            const imgData = viewMap[viewType];

            if (imgData) {
                const imgEl = card.querySelector('img');
                if (imgEl) {
                    imgEl.src = `${this.API_BASE}${imgData.file_path}`;
                    imgEl.classList.remove('blur-[1px]');
                }

                const badgeContainer = card.querySelector('div.flex.items-center.gap-1');
                if (badgeContainer) {
                    if (imgData.quality_status === 'GOOD') {
                        badgeContainer.className = 'flex items-center gap-1 text-status-green-text bg-status-green-bg px-2 py-1 rounded-sm';
                        badgeContainer.innerHTML = `
                            <span class="material-symbols-outlined text-[16px]" data-icon="check_circle" style="font-variation-settings: 'FILL' 1;">check_circle</span>
                            <span class="font-caption text-caption font-semibold">Good Quality (${Math.round(imgData.quality_score * 100)}%)</span>
                        `;
                    } else if (imgData.quality_status === 'WARNING') {
                        badgeContainer.className = 'flex items-center gap-1 text-status-amber-text bg-status-amber-bg px-2 py-1 rounded-sm';
                        badgeContainer.innerHTML = `
                            <span class="material-symbols-outlined text-[16px]" data-icon="warning" style="font-variation-settings: 'FILL' 1;">warning</span>
                            <span class="font-caption text-caption font-semibold">Warning (${Math.round(imgData.quality_score * 100)}%)</span>
                        `;
                    } else {
                        badgeContainer.className = 'flex items-center gap-1 text-status-red-text bg-status-red-bg px-2 py-1 rounded-sm';
                        badgeContainer.innerHTML = `
                            <span class="material-symbols-outlined text-[16px]" data-icon="error" style="font-variation-settings: 'FILL' 1;">error</span>
                            <span class="font-caption text-caption font-semibold">Blurry / Low Quality</span>
                        `;
                    }
                }
            }
        });
    },

    // 5. Analyzing Progress Controller
    async initAnalyzing() {
        if (!this.requireAuth()) return;

        const inspectionId = sessionStorage.getItem('active_inspection_id');
        if (!inspectionId) {
            window.location.href = '/stitch/code/02_dashboard.html';
            return;
        }

        try {
            await this.fetchAuth(`/api/inspections/${inspectionId}/ocr`, { method: 'POST' });
            setTimeout(() => {
                window.location.href = '/stitch/code/03_extracted_declarations.html';
            }, 1000);
        } catch (err) {
            alert(`Analysis error: ${err.message}`);
            window.location.href = '/stitch/code/09_capture_images_warning.html';
        }
    },

    // 6. Extracted Declarations Review Controller
    async initExtractedDeclarations() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        const inspectionId = sessionStorage.getItem('active_inspection_id');
        if (!inspectionId) {
            window.location.href = '/stitch/code/02_dashboard.html';
            return;
        }

        try {
            const res = await this.fetchAuth(`/api/inspections/${inspectionId}/declarations`);
            if (res.ok) {
                const declarations = await res.json();
                this.renderExtractedDeclarations(declarations);
            }
        } catch (err) {
            console.error('Failed to load declarations:', err);
        }

        const continueBtn = Array.from(document.querySelectorAll('button, a')).find(b => b.textContent.includes('Continue') || b.textContent.includes('Next') || b.textContent.includes('Review Findings'));
        if (continueBtn) {
            continueBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                continueBtn.textContent = 'Evaluating Legal Rules...';
                try {
                    await this.fetchAuth(`/api/inspections/${inspectionId}/evaluate`, { method: 'POST' });
                    window.location.href = '/stitch/code/05_findings.html';
                } catch (err) {
                    alert(`Evaluation failed: ${err.message}`);
                    window.location.href = '/stitch/code/05_findings.html';
                }
            });
        }
    },

    renderExtractedDeclarations(declarations) {
        const tableContainer = document.querySelector('main div.bg-surface.border.border-border-subtle.flex.flex-col');
        if (!tableContainer) return;

        tableContainer.innerHTML = '';

        const fieldLabels = {
            commodity_name: "Name of Commodity",
            manufacturer_details: "Manufacturer / Packer / Importer",
            net_quantity: "Net Quantity",
            mrp: "Maximum Retail Price (MRP)",
            date_of_manufacture_packing: "Month & Year of Manufacture / Packing",
            consumer_care_details: "Consumer Care Details",
            country_of_origin: "Country of Origin"
        };

        declarations.forEach(decl => {
            const row = document.createElement('div');
            row.className = 'flex flex-col p-base border-b border-border-subtle hover:bg-surface-variant transition-colors group';

            const label = fieldLabels[decl.field_name] || decl.field_name.replace(/_/g, ' ').toUpperCase();
            const valDisplay = decl.effective_value || decl.extracted_value || '<span class="text-secondary italic">Not Detected on Package</span>';

            let confBadge = '';
            if (decl.verification_status === 'CORRECTED') {
                confBadge = '<span class="font-caption text-caption text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-300">Verified by Inspector</span>';
            } else if (decl.extraction_status === 'NOT_FOUND') {
                confBadge = '<span class="font-caption text-caption text-secondary bg-slate-100 px-2 py-0.5 rounded border border-slate-300">Not Found</span>';
            } else if (decl.confidence >= 0.85) {
                confBadge = `<span class="font-caption text-caption text-status-green-text bg-status-green-bg px-2 py-0.5 rounded border border-status-green-text/20">OCR Confidence: High (${Math.round(decl.confidence * 100)}%)</span>`;
            } else {
                confBadge = `<span class="font-caption text-caption text-status-amber-text bg-status-amber-bg px-2 py-0.5 rounded border border-status-amber-text/20">Needs Manual Verification (${Math.round(decl.confidence * 100)}%)</span>`;
            }

            row.innerHTML = `
                <div class="flex justify-between items-start mb-tight">
                    <span class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">${label}</span>
                    <button class="text-primary hover:text-primary-container p-1 rounded-DEFAULT hover:bg-secondary-container transition-colors edit-decl-btn" title="Edit Declaration">
                        <span class="material-symbols-outlined text-[18px]" data-icon="edit">edit</span>
                    </button>
                </div>
                <div class="mb-2">
                    <span class="font-body-md text-body-md text-on-surface font-semibold decl-value-text">${valDisplay}</span>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                    <div class="flex items-center gap-1 bg-surface-container-low border border-border-subtle rounded-DEFAULT px-2 py-0.5">
                        <span class="material-symbols-outlined text-on-surface-variant text-[14px]" data-icon="memory">memory</span>
                        <span class="font-caption text-caption text-on-surface-variant">AI/OCR Extracted</span>
                    </div>
                    ${confBadge}
                </div>
            `;

            const editBtn = row.querySelector('.edit-decl-btn');
            editBtn.addEventListener('click', async () => {
                const currentVal = decl.effective_value || '';
                const newVal = prompt(`Verify / Correct ${label}:`, currentVal);
                if (newVal !== null && newVal.trim() !== currentVal) {
                    try {
                        const patchRes = await this.fetchAuth(`/api/declarations/${decl.id}`, {
                            method: 'PATCH',
                            body: JSON.stringify({ corrected_value: newVal.trim(), verification_status: 'CORRECTED' })
                        });
                        if (patchRes.ok) {
                            row.querySelector('.decl-value-text').textContent = newVal.trim();
                        }
                    } catch (err) {
                        alert(`Failed to update declaration: ${err.message}`);
                    }
                }
            });

            tableContainer.appendChild(row);
        });
    },

    // 7. Findings & Adjudication Controller (05_findings.html)
    async initFindings() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        const inspectionId = sessionStorage.getItem('active_inspection_id');
        if (!inspectionId) {
            window.location.href = '/stitch/code/02_dashboard.html';
            return;
        }

        const loadFindings = async () => {
            try {
                let res = await this.fetchAuth(`/api/inspections/${inspectionId}/findings`);
                let findings = await res.json();

                if (!findings || findings.length === 0) {
                    const evalRes = await this.fetchAuth(`/api/inspections/${inspectionId}/evaluate`, { method: 'POST' });
                    if (evalRes.ok) {
                        const evalData = await evalRes.json();
                        findings = evalData.findings;
                    }
                }

                this.renderFindings(findings);
            } catch (err) {
                console.error('Failed to load findings:', err);
            }
        };

        await loadFindings();

        const continueBtn = Array.from(document.querySelectorAll('button, a')).find(b => b.textContent.includes('Submit') || b.textContent.includes('Continue') || b.textContent.includes('Final Review'));
        if (continueBtn) {
            continueBtn.addEventListener('click', (e) => {
                e.preventDefault();
                window.location.href = '/stitch/code/13_step3_review_and_submit.html';
            });
        }
    },

    renderFindings(findings) {
        const container = document.querySelector('main div.flex.flex-col.gap-stack-md, main .space-y-4');
        if (!container) return;

        container.innerHTML = '';

        if (!findings || findings.length === 0) {
            container.innerHTML = '<div class="p-6 bg-white rounded border border-border-subtle text-center text-sm text-secondary">No statutory rule evaluations recorded.</div>';
            return;
        }

        findings.forEach(finding => {
            const card = document.createElement('div');
            
            let borderClass = 'border-border-subtle';
            let badgeHtml = '';
            
            if (finding.result_state === 'POTENTIAL_NON_COMPLIANCE') {
                borderClass = 'border-status-red-text ring-1 ring-status-red-text/30';
                badgeHtml = '<span class="font-caption text-caption bg-status-red-bg text-status-red-text px-2 py-0.5 rounded border border-status-red-text/20 font-bold">POTENTIAL NON-COMPLIANCE</span>';
            } else if (finding.result_state === 'PASS') {
                borderClass = 'border-status-green-text/50';
                badgeHtml = '<span class="font-caption text-caption bg-status-green-bg text-status-green-text px-2 py-0.5 rounded border border-status-green-text/20 font-bold">PASS</span>';
            } else if (finding.result_state === 'INSUFFICIENT_EVIDENCE') {
                borderClass = 'border-status-amber-text';
                badgeHtml = '<span class="font-caption text-caption bg-status-amber-bg text-status-amber-text px-2 py-0.5 rounded border border-status-amber-text/20 font-bold">INSUFFICIENT EVIDENCE</span>';
            } else {
                badgeHtml = '<span class="font-caption text-caption bg-slate-100 text-slate-700 px-2 py-0.5 rounded border border-slate-300">NOT APPLICABLE</span>';
            }

            let adjStatusHtml = '';
            if (finding.adjudication_status === 'CONFIRMED') {
                adjStatusHtml = '<span class="text-xs font-bold text-status-red-text">✓ Confirmed Violation by Inspector</span>';
            } else if (finding.adjudication_status === 'DISMISSED') {
                adjStatusHtml = '<span class="text-xs font-bold text-status-green-text">✗ Dismissed by Inspector</span>';
            }

            card.className = `p-4 bg-surface rounded-DEFAULT border ${borderClass} shadow-sm flex flex-col gap-3 transition-all`;
            card.innerHTML = `
                <div class="flex justify-between items-start">
                    <div>
                        <span class="font-label-caps text-label-caps text-secondary uppercase">${finding.rule_code}</span>
                        <h3 class="font-section-header text-section-header text-primary mt-0.5 font-bold">${finding.title}</h3>
                    </div>
                    <div class="flex flex-col items-end gap-1">
                        ${badgeHtml}
                        ${adjStatusHtml}
                    </div>
                </div>
                <p class="font-body-sm text-body-sm text-on-surface">${finding.explanation}</p>
                <div class="p-2 bg-surface-container-low rounded border border-border-subtle text-xs text-on-surface-variant flex justify-between items-center">
                    <span><strong>Effective Value Evaluated:</strong> ${finding.extracted_value || 'None / Not Detected'}</span>
                    <a href="/stitch/code/06_evidence_review.html" class="text-primary hover:underline font-semibold flex items-center gap-1">
                        <span class="material-symbols-outlined text-[14px]">visibility</span> View Evidence
                    </a>
                </div>
                <div class="flex items-center justify-end gap-2 pt-2 border-t border-border-subtle">
                    <button class="px-3 py-1.5 border border-border-subtle rounded text-xs font-bold hover:bg-slate-50 dismiss-btn text-secondary">Dismiss Finding</button>
                    <button class="px-3 py-1.5 bg-primary text-on-primary rounded text-xs font-bold hover:opacity-90 confirm-btn">Confirm Finding</button>
                </div>
            `;

            const confirmBtn = card.querySelector('.confirm-btn');
            const dismissBtn = card.querySelector('.dismiss-btn');

            confirmBtn.addEventListener('click', async () => {
                const notes = prompt('Inspector Note (Confirmation remarks):', finding.adjudication_notes || 'Confirmed statutory non-compliance on package display.');
                if (notes !== null) {
                    await this.fetchAuth(`/api/findings/${finding.id}/adjudicate`, {
                        method: 'PATCH',
                        body: JSON.stringify({ action: 'CONFIRMED', notes })
                    });
                    window.location.reload();
                }
            });

            dismissBtn.addEventListener('click', async () => {
                const notes = prompt('Reason for dismissal:', finding.adjudication_notes || 'Dismissed: Verified exemption under Rule 26.');
                if (notes !== null) {
                    await this.fetchAuth(`/api/findings/${finding.id}/adjudicate`, {
                        method: 'PATCH',
                        body: JSON.stringify({ action: 'DISMISSED', notes })
                    });
                    window.location.reload();
                }
            });

            container.appendChild(card);
        });
    },

    // 8. Evidence Review Controller (06_evidence_review.html)
    async initEvidenceReview() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        const inspectionId = sessionStorage.getItem('active_inspection_id');
        if (!inspectionId) {
            window.location.href = '/stitch/code/02_dashboard.html';
            return;
        }

        try {
            const [imgRes, findRes] = await Promise.all([
                this.fetchAuth(`/api/inspections/${inspectionId}/images`),
                this.fetchAuth(`/api/inspections/${inspectionId}/findings`)
            ]);

            if (imgRes.ok && findRes.ok) {
                const images = await imgRes.json();
                const findings = await findRes.json();
                this.renderEvidenceReview(images, findings);
            }
        } catch (err) {
            console.error('Failed to load evidence review:', err);
        }
    },

    renderEvidenceReview(images, findings) {
        if (images.length > 0) {
            const mainImg = document.querySelector('main img');
            if (mainImg) {
                mainImg.src = `${this.API_BASE}${images[0].file_path}`;
            }
        }
    },

    // 9. Step 3: Review & Submit (13_step3_review_and_submit.html)
    async initReviewAndSubmit() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        const inspectionId = sessionStorage.getItem('active_inspection_id');
        if (!inspectionId) {
            window.location.href = '/stitch/code/02_dashboard.html';
            return;
        }

        try {
            const inspRes = await this.fetchAuth(`/api/inspections/${inspectionId}`);
            if (inspRes.ok) {
                const insp = await inspRes.json();
                this.renderReviewSummary(insp);
            }
        } catch (err) {
            console.error('Failed to load summary:', err);
        }

        const finalizeBtn = Array.from(document.querySelectorAll('button, a')).find(b => 
            b.textContent.includes('Finalize') || b.textContent.includes('Submit') || b.textContent.includes('Generate Report') || b.textContent.includes('Sign')
        );

        if (finalizeBtn) {
            finalizeBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                finalizeBtn.disabled = true;
                finalizeBtn.textContent = 'Generating Statutory Report...';

                try {
                    const res = await this.fetchAuth(`/api/inspections/${inspectionId}/finalize`, {
                        method: 'POST',
                        body: JSON.stringify({ officer_notes: 'Finalized by Inspecting Officer after human adjudication.' })
                    });

                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Finalization failed');
                    }

                    window.location.href = '/stitch/code/07_inspection_report_preview.html';
                } catch (err) {
                    alert(`Error finalizing inspection: ${err.message}`);
                    finalizeBtn.disabled = false;
                    finalizeBtn.textContent = 'Submit & Finalize Inspection';
                }
            });
        }
    },

    renderReviewSummary(insp) {
        const prodH1 = document.querySelector('h1, h2');
        if (prodH1 && insp.product) {
            prodH1.textContent = `${insp.product.product_name} (${insp.inspection_number})`;
        }
    },

    // 10. Inspection Report Preview Controller (07_inspection_report_preview.html)
    async initReportPreview() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        const inspectionId = sessionStorage.getItem('active_inspection_id');
        if (!inspectionId) {
            window.location.href = '/stitch/code/02_dashboard.html';
            return;
        }

        try {
            const res = await this.fetchAuth(`/api/inspections/${inspectionId}/report`);
            if (res.ok) {
                const rep = await res.json();
                this.renderReportPreview(rep, inspectionId);
            }
        } catch (err) {
            console.error('Failed to load report metadata:', err);
        }

        const downloadBtns = Array.from(document.querySelectorAll('button, a')).find(b => 
            b.textContent.includes('Download') || b.textContent.includes('PDF') || b.textContent.includes('Export')
        );

        if (downloadBtns) {
            downloadBtns.addEventListener('click', (e) => {
                e.preventDefault();
                window.open(`${this.API_BASE}/api/inspections/${inspectionId}/report/pdf`, '_blank');
            });
        }
    },

    renderReportPreview(report, inspectionId) {
        const previewContainer = document.querySelector('main div.bg-surface, main div.border');
        if (previewContainer) {
            const dlLink = document.createElement('div');
            dlLink.className = 'p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-center justify-between mt-4';
            dlLink.innerHTML = `
                <div>
                    <p class="text-sm font-bold text-blue-950">Statutory PDF Inspection Report (v${report.report_version})</p>
                    <p class="text-xs text-blue-700">Official Department of Consumer Affairs Record • Generated ${new Date(report.generated_at).toLocaleString('en-GB')}</p>
                </div>
                <a href="${this.API_BASE}/api/inspections/${inspectionId}/report/pdf" target="_blank" class="px-4 py-2 bg-primary text-on-primary text-xs font-bold rounded hover:opacity-90 flex items-center gap-1">
                    <span class="material-symbols-outlined text-[16px]">download</span> Download PDF
                </a>
            `;
            previewContainer.prepend(dlLink);
        }
    },

    // 11. Reports List Controller (08_reports_list.html)
    async initReportsList() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        try {
            const res = await this.fetchAuth('/api/inspections');
            if (res.ok) {
                const inspections = await res.json();
                this.renderReportsList(inspections);
            }
        } catch (err) {
            console.error('Failed to load reports archive:', err);
        }
    },

    renderReportsList(inspections) {
        const container = document.querySelector('main div.flex.flex-col.gap-stack-sm, main .space-y-3');
        if (!container) return;

        container.innerHTML = '';

        if (!inspections || inspections.length === 0) {
            container.innerHTML = '<div class="p-8 text-center text-sm text-secondary bg-white rounded border">No inspection reports found in archive.</div>';
            return;
        }

        inspections.forEach(insp => {
            const card = document.createElement('div');
            card.className = 'p-4 bg-surface rounded-DEFAULT border border-border-subtle hover:border-primary/40 shadow-sm flex items-center justify-between transition-colors';
            
            let statusBadge = '<span class="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700">Draft</span>';
            if (insp.overall_status === 'POTENTIAL_NON_COMPLIANCE') {
                statusBadge = '<span class="text-xs font-bold px-2 py-0.5 rounded bg-status-red-bg text-status-red-text">Potential Non-Compliance</span>';
            } else if (insp.overall_status === 'NO_POTENTIAL_VIOLATIONS' || insp.overall_status === 'VERIFIED_COMPLIANT') {
                statusBadge = '<span class="text-xs font-bold px-2 py-0.5 rounded bg-status-green-bg text-status-green-text">Verified Compliant</span>';
            } else if (insp.overall_status === 'NEEDS_MANUAL_VERIFICATION') {
                statusBadge = '<span class="text-xs font-bold px-2 py-0.5 rounded bg-status-amber-bg text-status-amber-text">Needs Verification</span>';
            }

            const pName = insp.product ? insp.product.product_name : 'Packaged Commodity';
            const dateStr = new Date(insp.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

            card.innerHTML = `
                <div>
                    <div class="flex items-center gap-2">
                        <span class="font-mono text-xs font-bold text-primary">${insp.inspection_number}</span>
                        ${statusBadge}
                    </div>
                    <h3 class="font-body-md text-on-surface font-semibold mt-1">${pName}</h3>
                    <p class="text-xs text-on-surface-variant">${insp.location} • ${dateStr}</p>
                </div>
                <div class="flex items-center gap-2">
                    <button class="px-3 py-1.5 border border-border-subtle rounded text-xs font-bold hover:bg-slate-50 view-btn text-primary">View Report</button>
                    <a href="${this.API_BASE}/api/inspections/${insp.id}/report/pdf" target="_blank" class="px-3 py-1.5 bg-primary text-on-primary rounded text-xs font-bold hover:opacity-90 flex items-center gap-1">
                        <span class="material-symbols-outlined text-[14px]">download</span> PDF
                    </a>
                </div>
            `;

            card.querySelector('.view-btn').addEventListener('click', () => {
                sessionStorage.setItem('active_inspection_id', insp.id);
                window.location.href = '/stitch/code/07_inspection_report_preview.html';
            });

            container.appendChild(card);
        });
    },

    // 12. Profile Controller
    initProfile() {
        if (!this.requireAuth()) return;
        this.initCommonNav();

        const profile = this.getProfile();
        
        const nameEl = document.querySelector('h1, h2.font-headline-lg');
        if (nameEl && profile.full_name) {
            nameEl.textContent = profile.full_name;
        }

        const logoutBtn = Array.from(document.querySelectorAll('button, a')).find(el => el.textContent.toLowerCase().includes('log out') || el.textContent.toLowerCase().includes('logout'));
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (confirm('Are you sure you want to sign out?')) {
                    this.logout();
                }
            });
        }
    },

    // Common Navigation Controller
    initCommonNav() {
        const newInspBtns = document.querySelectorAll('button, a');
        newInspBtns.forEach(btn => {
            const text = btn.textContent.trim().toUpperCase();
            if (text.includes('NEW INSPECTION') || btn.querySelector('[data-icon="add"]')) {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    window.location.href = '/stitch/code/04_new_inspection_step1.html';
                });
            }
        });

        const navItems = document.querySelectorAll('nav a, nav div.cursor-pointer');
        navItems.forEach(item => {
            const text = item.textContent.toLowerCase();
            if (text.includes('home')) {
                item.addEventListener('click', () => window.location.href = '/stitch/code/02_dashboard.html');
            } else if (text.includes('inspections') || text.includes('reports')) {
                item.addEventListener('click', () => window.location.href = '/stitch/code/08_reports_list.html');
            } else if (text.includes('new')) {
                item.addEventListener('click', () => window.location.href = '/stitch/code/04_new_inspection_step1.html');
            } else if (text.includes('profile')) {
                item.addEventListener('click', () => window.location.href = '/stitch/code/10_profile.html');
            }
        });

        const backBtns = document.querySelectorAll('[data-icon="arrow_back"], button:has([data-icon="arrow_back"])');
        backBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                if (window.history.length > 1) {
                    window.history.back();
                } else {
                    window.location.href = '/stitch/code/02_dashboard.html';
                }
            });
        });
    }
};

document.addEventListener('DOMContentLoaded', () => App.init());
