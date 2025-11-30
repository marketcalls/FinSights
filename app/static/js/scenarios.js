/**
 * AI Scenarios Feature - Client-side JavaScript
 */

class ScenarioManager {
    constructor() {
        this.currentNewsId = null;
        this.isGenerating = false;
        this.init();
    }

    init() {
        // Extract news ID from URL if on news detail page
        const pathMatch = window.location.pathname.match(/\/news\/(\d+)/);
        if (pathMatch) {
            this.currentNewsId = parseInt(pathMatch[1]);
            this.checkExistingScenarios();
        }
    }

    async checkExistingScenarios() {
        try {
            const response = await fetch(`/news/${this.currentNewsId}/scenarios`);
            const data = await response.json();
            
            if (data.scenarios && data.scenarios.length > 0) {
                this.displayScenarios(data.scenarios);
            }
        } catch (error) {
            console.error('Error checking scenarios:', error);
        }
    }

    async generateScenarios() {
        if (this.isGenerating) return;
        
        this.isGenerating = true;
        const button = document.getElementById('generate-scenarios-btn');
        const container = document.getElementById('scenarios-container');
        
        // Update button state
        button.disabled = true;
        button.innerHTML = '<span class="loading loading-spinner loading-sm"></span> Generating...';
        
        // Show loading message
        container.innerHTML = `
            <div class="alert alert-info">
                <span class="loading loading-spinner"></span>
                <span>AI is analyzing this news and generating alternative scenarios... This may take 5-10 seconds.</span>
            </div>
        `;
        container.classList.remove('hidden');
        
        try {
            const response = await fetch(`/news/${this.currentNewsId}/scenarios`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    num_scenarios: 3
                })
            });
            
            const data = await response.json();
            
            if (data.scenarios && data.scenarios.length > 0) {
                this.displayScenarios(data.scenarios);
                button.innerHTML = '✓ Scenarios Generated';
                button.classList.add('btn-success');
            } else {
                throw new Error('No scenarios generated');
            }
        } catch (error) {
            console.error('Error generating scenarios:', error);
            container.innerHTML = `
                <div class="alert alert-error">
                    <span>⚠️</span>
                    <span>Failed to generate scenarios. Please try again later.</span>
                </div>
            `;
            button.disabled = false;
            button.innerHTML = '🤖 Generate AI Scenarios';
        } finally {
            this.isGenerating = false;
        }
    }

    displayScenarios(scenarios) {
        const container = document.getElementById('scenarios-container');
        
        const scenariosHTML = scenarios.map((scenario, index) => {
            const probabilityPercent = Math.round((scenario.probability || 0) * 100);
            const probabilityClass = probabilityPercent > 50 ? 'badge-success' : 
                                     probabilityPercent > 25 ? 'badge-warning' : 'badge-error';
            
            return `
                <div class="card bg-base-100 shadow-sm mb-4 scenario-card" data-scenario-id="${scenario.id}">
                    <div class="card-body p-4">
                        <div class="flex items-start justify-between gap-3">
                            <h4 class="font-semibold text-lg flex items-center gap-2">
                                <span class="text-2xl">${this.getScenarioIcon(index)}</span>
                                ${scenario.title}
                            </h4>
                            <div class="badge ${probabilityClass} badge-lg">
                                ${probabilityPercent}% likely
                            </div>
                        </div>
                        
                        <p class="text-sm mt-3 opacity-90">${scenario.description}</p>
                        
                        ${this.renderImpactAnalysis(scenario.impact_analysis)}
                        
                        ${scenario.historical_context ? `
                            <details class="text-xs mt-3 opacity-70">
                                <summary class="cursor-pointer font-semibold">📚 Historical Context</summary>
                                <p class="mt-2 pl-4 border-l-2 border-base-300">${scenario.historical_context}</p>
                            </details>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = `
            <div class="divider">Generated Scenarios</div>
            ${scenariosHTML}
        `;
        container.classList.remove('hidden');
    }

    renderImpactAnalysis(impactAnalysis) {
        if (!impactAnalysis) return '';
        
        let html = '<div class="mt-4">';
        
        // Sectors impact
        if (impactAnalysis.sectors && Object.keys(impactAnalysis.sectors).length > 0) {
            html += '<div class="mb-2"><strong class="text-xs opacity-70">Sector Impact:</strong></div>';
            html += '<div class="flex flex-wrap gap-2 mb-3">';
            
            for (const [sector, impact] of Object.entries(impactAnalysis.sectors)) {
                const isPositive = impact.includes('+');
                const badgeClass = isPositive ? 'badge-success' : 'badge-error';
                html += `
                    <div class="badge ${badgeClass} badge-sm gap-1">
                        ${isPositive ? '📈' : '📉'} ${sector}: ${impact}
                    </div>
                `;
            }
            html += '</div>';
        }
        
        // Indices impact
        if (impactAnalysis.indices && Object.keys(impactAnalysis.indices).length > 0) {
            html += '<div class="mb-2"><strong class="text-xs opacity-70">Index Impact:</strong></div>';
            html += '<div class="flex flex-wrap gap-2">';
            
            for (const [index, impact] of Object.entries(impactAnalysis.indices)) {
                const isPositive = impact.includes('+');
                const badgeClass = isPositive ? 'badge-success' : 'badge-error';
                html += `
                    <div class="badge ${badgeClass} badge-sm gap-1">
                        ${index.toUpperCase()}: ${impact}
                    </div>
                `;
            }
            html += '</div>';
        }
        
        html += '</div>';
        return html;
    }

    getScenarioIcon(index) {
        const icons = ['🎯', '⚡', '🔮'];
        return icons[index] || '📊';
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.scenarioManager = new ScenarioManager();
    });
} else {
    window.scenarioManager = new ScenarioManager();
}

// Global function for button onclick
function generateScenarios() {
    if (window.scenarioManager) {
        window.scenarioManager.generateScenarios();
    }
}
