// Custom JavaScript for Insurance Management Tool

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });
    
    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl)
    });
    
    // Toast function
    window.showToast = function(message, type = 'success') {
        const toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) return;
        
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        toast.setAttribute('aria-atomic', 'true');
        
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;
        
        toastContainer.appendChild(toast);
        const bsToast = new bootstrap.Toast(toast, {
            autohide: true,
            delay: 3000
        });
        bsToast.show();
        
        // Remove toast after it's hidden
        toast.addEventListener('hidden.bs.toast', function() {
            toast.remove();
        });
    };
    
    // Handle editable cells in tables
    document.querySelectorAll('.editable-cell').forEach(cell => {
        cell.addEventListener('dblclick', function() {
            const value = this.textContent.trim();
            const field = this.dataset.field;
            const id = this.dataset.id;
            
            // Create input for editing
            const input = document.createElement('input');
            input.type = 'text';
            input.value = value;
            input.className = 'form-control form-control-sm';
            input.style.width = '100%';
            
            // Replace cell content with input
            const originalContent = this.innerHTML;
            this.innerHTML = '';
            this.appendChild(input);
            input.focus();
            
            // Handle input blur (save changes)
            input.addEventListener('blur', function() {
                cell.innerHTML = originalContent;
                
                // If value changed, save it
                if (this.value !== value) {
                    // Here you would typically make an AJAX call to save the changes
                    // For now, just update the display
                    cell.textContent = this.value;
                    showToast(`Campo ${field} aggiornato`, 'success');
                }
            });
            
            // Handle Enter key
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    this.blur();
                } else if (e.key === 'Escape') {
                    cell.innerHTML = originalContent;
                }
            });
        });
    });
    
    // Initialize Select2 for dropdowns
    if (typeof $.fn.select2 !== 'undefined') {
        $('.select2').select2({
            theme: 'bootstrap-5'
        });
    }
});