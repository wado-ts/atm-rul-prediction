/**
 * Auth Page JavaScript
 * Handles view switching, form validation, password strength, and UI interactions
 */

(function() {
  'use strict';

  // DOM Elements
  const views = {
    login: document.getElementById('login-view'),
    register: document.getElementById('register-view'),
    forgot: document.getElementById('forgot-view')
  };

  const forms = {
    login: document.querySelector('[data-form="login"]'),
    register: document.querySelector('[data-form="register"]'),
    forgot: document.querySelector('[data-form="forgot"]')
  };

  // View Switching
  function switchView(viewName) {
    // Hide all views
    Object.values(views).forEach(view => {
      if (view) view.classList.add('hidden');
    });

    // Show target view
    if (views[viewName]) {
      views[viewName].classList.remove('hidden');
    }

    // Update URL without reload
    const url = new URL(window.location);
    if (viewName === 'login') {
      url.pathname = '/auth/login';
    } else if (viewName === 'register') {
      url.pathname = '/auth/register';
    } else if (viewName === 'forgot') {
      url.pathname = '/auth/forgot-password';
    }
    window.history.replaceState({}, '', url);
  }

  // Initialize view from URL
  function initViewFromURL() {
    const path = window.location.pathname;
    if (path.includes('/register')) {
      switchView('register');
    } else if (path.includes('/forgot')) {
      switchView('forgot');
    } else {
      switchView('login');
    }
  }

  // Password Toggle
  function initPasswordToggles() {
    document.querySelectorAll('.password-toggle').forEach(toggle => {
      toggle.addEventListener('click', function() {
        const input = this.previousElementSibling;
        const isPassword = input.type === 'password';
        
        input.type = isPassword ? 'text' : 'password';
        this.classList.toggle('show-password', isPassword);
        this.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');
      });
    });
  }

  // Email Validation
  function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  // Password Strength Calculator
  function calculatePasswordStrength(password) {
    let strength = 0;
    
    if (password.length >= 8) strength += 1;
    if (password.length >= 12) strength += 1;
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength += 1;
    if (/\d/.test(password)) strength += 1;
    if (/[^a-zA-Z0-9]/.test(password)) strength += 1;
    
    return strength;
  }

  // Password Strength UI Update
  function updatePasswordStrength(password) {
    const strengthFill = document.getElementById('strength-fill');
    const strengthText = document.getElementById('strength-text');
    
    if (!strengthFill || !strengthText) return;

    const strength = calculatePasswordStrength(password);
    
    // Update width
    const percentage = (strength / 5) * 100;
    strengthFill.style.width = percentage + '%';
    
    // Update color and text
    strengthFill.classList.remove('weak', 'medium', 'strong');
    
    if (strength <= 2) {
      strengthFill.classList.add('weak');
      strengthText.textContent = 'Weak password';
    } else if (strength <= 3) {
      strengthFill.classList.add('medium');
      strengthText.textContent = 'Medium password';
    } else {
      strengthFill.classList.add('strong');
      strengthText.textContent = 'Strong password';
    }
  }

  // Form Validation
  function validateLoginForm() {
    const email = document.getElementById('login-email');
    const password = document.getElementById('login-password');
    let isValid = true;

    if (!isValidEmail(email.value)) {
      email.style.borderColor = 'var(--risk-critical-border)';
      isValid = false;
    } else {
      email.style.borderColor = '';
    }

    if (password.value.length < 1) {
      password.style.borderColor = 'var(--risk-critical-border)';
      isValid = false;
    } else {
      password.style.borderColor = '';
    }

    return isValid;
  }

  function validateRegisterForm() {
    const email = document.getElementById('register-email');
    const password = document.getElementById('register-password');
    const confirm = document.getElementById('register-confirm');
    const emailError = document.getElementById('email-error');
    const confirmError = document.getElementById('confirm-error');
    
    let isValid = true;

    // Email validation
    if (!isValidEmail(email.value)) {
      email.style.borderColor = 'var(--risk-critical-border)';
      if (emailError) emailError.textContent = 'Please enter a valid email address';
      isValid = false;
    } else {
      email.style.borderColor = '';
      if (emailError) emailError.textContent = '';
    }

    // Password validation
    if (password.value.length < 8) {
      password.style.borderColor = 'var(--risk-critical-border)';
      isValid = false;
    } else {
      password.style.borderColor = '';
    }

    // Confirm password validation
    if (password.value !== confirm.value) {
      confirm.style.borderColor = 'var(--risk-critical-border)';
      if (confirmError) confirmError.textContent = 'Passwords do not match';
      isValid = false;
    } else {
      confirm.style.borderColor = '';
      if (confirmError) confirmError.textContent = '';
    }

    return isValid;
  }

  // Form Submission Handling
  function initFormSubmissions() {
    // Login form
    if (forms.login) {
      forms.login.addEventListener('submit', function(e) {
        if (!validateLoginForm()) {
          e.preventDefault();
          return;
        }
        
        const btn = this.querySelector('[data-submit="login"]');
        if (btn) {
          btn.classList.add('loading');
        }
      });
    }

    // Register form
    if (forms.register) {
      const passwordInput = document.getElementById('register-password');
      
      // Real-time password strength
      if (passwordInput) {
        passwordInput.addEventListener('input', function() {
          updatePasswordStrength(this.value);
        });
      }

      forms.register.addEventListener('submit', function(e) {
        if (!validateRegisterForm()) {
          e.preventDefault();
          return;
        }
        
        const btn = this.querySelector('[data-submit="register"]');
        if (btn) {
          btn.classList.add('loading');
        }
      });
    }

    // Forgot password form
    if (forms.forgot) {
      forms.forgot.addEventListener('submit', function(e) {
        const email = document.getElementById('forgot-email');
        
        if (!isValidEmail(email.value)) {
          e.preventDefault();
          email.style.borderColor = 'var(--risk-critical-border)';
          return;
        }
        
        email.style.borderColor = '';
        
        const btn = this.querySelector('[data-submit="forgot"]');
        if (btn) {
          btn.classList.add('loading');
        }
      });
    }
  }

  // View Switch Buttons
  function initViewSwitchers() {
    document.querySelectorAll('[data-switch]').forEach(button => {
      button.addEventListener('click', function(e) {
        e.preventDefault();
        const targetView = this.getAttribute('data-switch');
        switchView(targetView);
      });
    });
  }

  // Input Focus Effects
  function initInputEffects() {
    document.querySelectorAll('.form-group input').forEach(input => {
      input.addEventListener('focus', function() {
        this.style.borderColor = '';
      });
      
      input.addEventListener('blur', function() {
        if (this.value.length > 0) {
          this.style.borderColor = 'var(--grey-line)';
        }
      });
    });
  }

  // Initialize Everything
  function init() {
    initViewFromURL();
    initPasswordToggles();
    initFormSubmissions();
    initViewSwitchers();
    initInputEffects();
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
