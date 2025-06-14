document.addEventListener('DOMContentLoaded', () => {
    const autoBtn = document.getElementById('auto-detect-btn');
    const previewBtn = document.getElementById('preview-btn');
    const saveBtn = document.getElementById('save-btn');
    const mappingSection = document.getElementById('mapping-section');
    const previewSection = document.getElementById('preview-section');
    const previewList = document.getElementById('preview-list');

    const urlInput = document.getElementById('website-url');
    const nameInput = document.getElementById('feed-name');

    const fields = ['item_selector', 'title_selector', 'link_selector', 'content_selector', 'date_selector', 'author_selector'];

    // Initialize pick buttons with new CSS classes
    const pickerButtons = {};
    fields.forEach(f => {
        const existingBtn = document.querySelector(`[data-field="${f}"]`);
        if (existingBtn) {
            pickerButtons[f] = existingBtn;
        } else {
            // If a pick button already exists in markup, do not add another
            let btn = document.getElementById(f).parentElement.querySelector('[data-field="'+f+'"]');
            if (!btn) {
                btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = 'Pick';
                btn.style.marginLeft = '4px';
                btn.addEventListener('click', () => openPicker(f));
                document.getElementById(f).parentElement.appendChild(btn);
            }
            pickerButtons[f] = btn;
        }
    });

    // Initialize preview tabs
    document.querySelectorAll('.preview-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const targetTab = tab.dataset.tab;
            
            // Update active tab
            document.querySelectorAll('.preview-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            // Show/hide content
            document.querySelectorAll('.preview-content').forEach(content => {
                content.classList.add('hidden');
            });
            document.getElementById(`preview-${targetTab}`).classList.remove('hidden');
        });
    });

    function openPicker(field) {
        const urlVal = urlInput.value.trim();
        if (!urlVal) { alert('Enter URL first'); return; }
        // Ensure mapping section is shown so user sees selector fields
        mappingSection.style.display = 'block';
        const itemSel = document.getElementById('item_selector').value.trim();
        const qsItem = itemSel ? '&item_sel='+encodeURIComponent(itemSel) : '';
        window.open('/picker?url='+encodeURIComponent(urlVal)+'&field='+field+qsItem, '_blank', 'width=800,height=600');
    }

    window.addEventListener('message', (event) => {
        if (event.data && event.data.field && event.data.selector) {
            const input = document.getElementById(event.data.field);
            if (input) { 
                input.value = event.data.selector;
                showAlert(`✅ ${event.data.field.replace('_', ' ')} selector updated`, 'success');
                // Auto preview to reflect change
                fetchPreview();
            }
        }
    });

    autoBtn.addEventListener('click', async () => {
        const urlVal = urlInput.value.trim();
        if (!urlVal) {
            showAlert('Please enter a website URL', 'error');
            urlInput.focus();
            return;
        }
        
        setButtonLoading(autoBtn, '🤖 Analyzing Website...', true);
        
        try {
            const resp = await fetch('/api/auto_detect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: urlVal})
            });
            const data = await resp.json();
            
            if (resp.ok) {
                // Show mapping section with animation
                mappingSection.classList.remove('hidden');
                mappingSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                
                const mapping = data.mapping;
                fields.forEach(f => {
                    document.getElementById(f).value = mapping[f] || '';
                });
                
                if (data.preview) {
                    await fetchPreview();
                }
                
                showAlert('🎉 Content structure detected successfully!', 'success');
            } else {
                showAlert('❌ Auto-detection failed: ' + data.error, 'error');
            }
        } catch (err) {
            showAlert('❌ Network error: ' + err.message, 'error');
        } finally {
            setButtonLoading(autoBtn, '🤖 Auto-Detect Content Structure', false);
        }
    });

    previewBtn.addEventListener('click', async () => {
        await fetchPreview();
    });

    async function fetchPreview() {
        const urlVal = urlInput.value.trim();
        const mapping = getMapping();
        
        if (!urlVal) {
            showAlert('Please enter a website URL', 'error');
            return;
        }
        
        setButtonLoading(previewBtn, '👁️ Loading Preview...', true);
        
        try {
            const resp = await fetch('/api/preview', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: urlVal, mapping})
            });
            const data = await resp.json();
            
            if (resp.ok) {
                renderPreview(data.items);
                previewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                // Show alert near the preview section instead of at the top
                showAlertNear('✅ Preview updated successfully', 'success', previewSection);
            } else {
                showAlert('❌ Preview failed: ' + data.error, 'error');
            }
        } catch (err) {
            showAlert('❌ Network error: ' + err.message, 'error');
        } finally {
            setButtonLoading(previewBtn, '👁️ Preview Content', false);
        }
    }

    function renderPreview(items) {
        previewSection.classList.remove('hidden');
        previewList.innerHTML = '';
        
        if (!items || items.length === 0) {
            previewList.innerHTML = '<div class="rss-empty-state"><em style="color: var(--text-muted);">No items detected. Try adjusting your selectors.</em></div>';
            return;
        }
        
        const siteURL = urlInput.value.trim();
        
        // Create RSS feed header
        const feedHeader = document.createElement('div');
        feedHeader.className = 'rss-feed-header';
        feedHeader.innerHTML = `
            <div class="rss-feed-title">
                <h3 style="margin: 0; color: var(--accent-primary); font-size: 1.5rem;">📡 ${siteURL.replace(/^https?:\/\//, '').split('/')[0]}</h3>
                <p style="margin: 0.5rem 0 0 0; color: var(--text-muted); font-size: 0.9rem;">RSS Feed Preview • ${items.length} item${items.length !== 1 ? 's' : ''}</p>
            </div>
            <div class="rss-feed-meta">
                <span style="background: var(--accent-light); color: var(--accent-primary); padding: 0.25rem 0.75rem; border-radius: 1rem; font-size: 0.75rem; font-weight: 600;">PREVIEW</span>
            </div>
        `;
        previewList.appendChild(feedHeader);
        
        items.forEach((item, index) => {
            const article = document.createElement('article');
            article.className = 'rss-feed-item';
            
            // Create article header with title and metadata
            const header = document.createElement('header');
            header.className = 'rss-item-header';
            
            const title = document.createElement('h4');
            title.className = 'rss-item-title';
            
            if (item.link) {
                const link = document.createElement('a');
                link.href = item.link;
                link.textContent = item.title || `Article ${index + 1}`;
                link.target = '_blank';
                link.style.textDecoration = 'none';
                link.style.color = 'var(--text-primary)';
                title.appendChild(link);
            } else {
                title.textContent = item.title || `Article ${index + 1}`;
            }
            
            header.appendChild(title);
            
            // Add metadata row
            const meta = document.createElement('div');
            meta.className = 'rss-item-meta';
            
            const metaItems = [];
            
            if (item.author) {
                metaItems.push(`👤 ${item.author}`);
            }
            
            if (item.date) {
                metaItems.push(`📅 ${new Date(item.date).toLocaleDateString()}`);
            } else {
                metaItems.push(`📅 ${new Date().toLocaleDateString()}`);
            }
            
            metaItems.push(`🔗 ${item.link ? new URL(item.link).hostname : siteURL.replace(/^https?:\/\//, '').split('/')[0]}`);
            
            meta.innerHTML = metaItems.join(' • ');
            header.appendChild(meta);
            
            article.appendChild(header);
            
            // Add content preview
            if (item.content) {
                const content = document.createElement('div');
                content.className = 'rss-item-content';
                
                const contentText = item.content.length > 200 ? 
                    item.content.substring(0, 200) + '...' : item.content;
                
                content.innerHTML = `
                    <p>${contentText}</p>
                    ${item.link ? `<a href="${item.link}" target="_blank" class="rss-read-more">Read full article →</a>` : ''}
                `;
                
                article.appendChild(content);
            }
            
            // Add action footer
            const footer = document.createElement('footer');
            footer.className = 'rss-item-footer';
            footer.innerHTML = `
                <div class="rss-item-actions">
                    ${item.link ? `<a href="${item.link}" target="_blank" class="rss-action-btn">📖 Read</a>` : ''}
                    <button type="button" class="rss-action-btn" onclick="shareArticle('${item.title}', '${item.link}')">📤 Share</button>
                </div>
            `;
            
            article.appendChild(footer);
            previewList.appendChild(article);
        });
    }

    function getMapping() {
        const mapping = {};
        fields.forEach(f => {
            mapping[f] = document.getElementById(f).value.trim();
        });
        return mapping;
    }

    saveBtn.addEventListener('click', async () => {
        const name = nameInput.value.trim();
        const urlVal = urlInput.value.trim();
        const mapping = getMapping();
        
        if (!name) {
            showAlert('Please enter a feed name', 'error');
            nameInput.focus();
            return;
        }
        if (!urlVal) {
            showAlert('Please enter a website URL', 'error');
            urlInput.focus();
            return;
        }
        if (!mapping.item_selector) {
            showAlert('Please configure the item selector first', 'error');
            return;
        }
        
        setButtonLoading(saveBtn, '💾 Creating Feed...', true);
        
        try {
            const payload = {
                name: name,
                url: urlVal,
                ...mapping
            };
            const resp = await fetch('/api/feeds', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const data = await resp.json();
            
            if (resp.ok) {
                showAlert('🎉 RSS Feed created successfully! Redirecting...', 'success');
                setTimeout(() => {
                    window.location.href = '/feeds/' + data.id;
                }, 1500);
            } else {
                showAlert('❌ Save failed: ' + data.error, 'error');
            }
        } catch (err) {
            showAlert('❌ Network error: ' + err.message, 'error');
        } finally {
            setButtonLoading(saveBtn, '💾 Save RSS Feed', false);
        }
    });

    // Utility functions
    function setButtonLoading(button, originalText, isLoading) {
        if (isLoading) {
            button.disabled = true;
            button.classList.add('btn-loading');
            button.setAttribute('data-original-text', button.textContent);
            button.textContent = originalText;
        } else {
            button.disabled = false;
            button.classList.remove('btn-loading');
            button.textContent = originalText;
        }
    }

    function showAlert(message, type = 'info') {
        showToast(message, type);
    }

    function showAlertNear(message, type = 'info', targetElement) {
        // Remove existing contextual alerts
        const existingAlerts = document.querySelectorAll('.alert-contextual');
        existingAlerts.forEach(alert => alert.remove());
        
        // Create new contextual alert
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-contextual`;
        alert.textContent = message;
        alert.style.marginBottom = '1rem';
        
        // Insert before the target element
        targetElement.parentNode.insertBefore(alert, targetElement);
        
        // Auto-remove after 3 seconds (shorter since it's contextual)
        setTimeout(() => {
            if (alert.parentNode) {
                alert.remove();
            }
        }, 3000);
        
        // Don't scroll - the user is already at the right location
    }

    function showToast(message, type = 'info') {
        // Create toast container if it doesn't exist
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        
        // Create toast
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icon = getToastIcon(type);
        
        toast.innerHTML = `
            <span class="toast-icon">${icon}</span>
            <span class="toast-content">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">×</button>
        `;
        
        container.appendChild(toast);
        
        // Auto-remove after 4 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 4000);
    }

    function getToastIcon(type) {
        switch (type) {
            case 'success': return '🎉';
            case 'error': return '❌';
            case 'info': return 'ℹ️';
            default: return 'ℹ️';
        }
    }

    function copyPreviewXML() {
        const xmlContent = document.getElementById('rss-xml-content').textContent;
        if (xmlContent.includes('Save the feed first')) {
            showAlert('💡 Please save the feed first to get the RSS XML', 'info');
            return;
        }
        
        navigator.clipboard.writeText(xmlContent).then(() => {
            showAlert('📋 RSS XML copied to clipboard!', 'success');
        }).catch(() => {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = xmlContent;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            showAlert('📋 RSS XML copied to clipboard!', 'success');
        });
    }

    function shareArticle(title, url) {
        if (navigator.share && url) {
            navigator.share({
                title: title,
                url: url
            }).catch(() => {
                // Fallback to copying URL
                copyToClipboard(url);
            });
        } else if (url) {
            copyToClipboard(url);
        } else {
            showAlert('No URL available to share', 'info');
        }
    }

    function copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            showAlert('📋 URL copied to clipboard!', 'success');
        }).catch(() => {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            showAlert('📋 URL copied to clipboard!', 'success');
        });
    }

    // Make functions globally available
    window.copyPreviewXML = copyPreviewXML;
    window.shareArticle = shareArticle;
}); 