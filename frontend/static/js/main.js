// 平滑滚动
function smoothScroll() {
    const links = document.querySelectorAll('a[href^="#"]');
    
    links.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;
            
            const targetElement = document.querySelector(targetId);
            if (targetElement) {
                window.scrollTo({
                    top: targetElement.offsetTop - 80,
                    behavior: 'smooth'
                });
            }
        });
    });
}

// 导航栏滚动效果
function navbarScrollEffect() {
    const navbar = document.querySelector('.navbar');
    
    window.addEventListener('scroll', function() {
        if (window.scrollY > 50) {
            navbar.style.backgroundColor = 'rgba(255, 255, 255, 0.95)';
            navbar.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.1)';
        } else {
            navbar.style.backgroundColor = 'white';
            navbar.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.1)';
        }
    });
}

// 功能卡片悬停效果
function featureCardEffects() {
    const cards = document.querySelectorAll('.feature-card');
    
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-10px)';
            this.style.boxShadow = '0 10px 20px rgba(0, 0, 0, 0.1)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.05)';
        });
    });
}

// 定价卡片切换效果
function pricingCardEffects() {
    const cards = document.querySelectorAll('.pricing-card');
    
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-10px)';
        });
        
        card.addEventListener('mouseleave', function() {
            if (!this.classList.contains('featured')) {
                this.style.transform = 'translateY(0)';
            }
        });
    });
}

// 表单验证
function validateForms() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const inputs = form.querySelectorAll('input[required], textarea[required]');
            let isValid = true;
            
            inputs.forEach(input => {
                if (!input.value.trim()) {
                    isValid = false;
                    input.style.borderColor = '#dc3545';
                    input.style.boxShadow = '0 0 0 0.2rem rgba(220, 53, 69, 0.25)';
                } else {
                    input.style.borderColor = '#ced4da';
                    input.style.boxShadow = 'none';
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                alert('请填写所有必填字段');
            }
        });
        
        // 输入框焦点效果
        const inputs = form.querySelectorAll('input, textarea');
        inputs.forEach(input => {
            input.addEventListener('focus', function() {
                this.style.borderColor = '#007bff';
                this.style.boxShadow = '0 0 0 0.2rem rgba(0, 123, 255, 0.25)';
            });
            
            input.addEventListener('blur', function() {
                if (this.value.trim()) {
                    this.style.borderColor = '#28a745';
                    this.style.boxShadow = '0 0 0 0.2rem rgba(40, 167, 69, 0.25)';
                } else {
                    this.style.borderColor = '#ced4da';
                    this.style.boxShadow = 'none';
                }
            });
        });
    });
}

// 订阅表单处理
function handleSubscribeForm() {
    const subscribeForm = document.querySelector('.subscribe-form');
    if (subscribeForm) {
        subscribeForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const emailInput = this.querySelector('input[type="email"]');
            const email = emailInput.value.trim();
            
            if (email && validateEmail(email)) {
                alert('感谢您的订阅！我们会定期向您发送平台动态和营销趋势。');
                emailInput.value = '';
            } else {
                alert('请输入有效的邮箱地址');
                emailInput.style.borderColor = '#dc3545';
            }
        });
    }
}

// 邮箱验证
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

// 加载动画
function loadingAnimation() {
    window.addEventListener('load', function() {
        document.body.style.opacity = '0';
        document.body.style.transition = 'opacity 0.5s ease';
        
        setTimeout(() => {
            document.body.style.opacity = '1';
        }, 100);
    });
}

// 加载首页配置
async function loadHomepageConfig() {
    try {
        const response = await fetch('/api/v1/public/config');
        if (!response.ok) return;
        const payload = await response.json();
        const homepage = payload?.homepage;
        if (!homepage) return;

        const siteLogo = document.getElementById('site-logo');
        const heroTitle = document.getElementById('hero-title');
        const heroSubtitle = document.getElementById('hero-subtitle');
        const heroImage = document.getElementById('hero-image');
        const heroPrimaryBtn = document.getElementById('hero-primary-btn');
        const heroSecondaryBtn = document.getElementById('hero-secondary-btn');
        const contactTitle = document.getElementById('contact-title');
        const contactSubtitle = document.getElementById('contact-subtitle');
        const contactAddress = document.getElementById('contact-address');
        const contactPhone = document.getElementById('contact-phone');
        const contactEmail = document.getElementById('contact-email');
        const merchantQuickNote = document.getElementById('merchant-quick-note');
        const merchantNoticeTitle = document.getElementById('merchant-notice-title');
        const merchantNoticeText = document.getElementById('merchant-notice-text');
        const merchantServicePublish = document.getElementById('merchant-service-publish');
        const merchantServiceAccount = document.getElementById('merchant-service-account');
        const merchantServiceNoRegister = document.getElementById('merchant-service-no-register');
        const merchantContactPhone = document.getElementById('merchant-contact-phone');
        const merchantContactWechat = document.getElementById('merchant-contact-wechat');
        const merchantContactEmail = document.getElementById('merchant-contact-email');

        if (siteLogo && homepage.nav_brand) siteLogo.textContent = homepage.nav_brand;
        if (heroTitle && homepage.hero_title) heroTitle.textContent = homepage.hero_title;
        if (heroSubtitle && homepage.hero_subtitle) heroSubtitle.textContent = homepage.hero_subtitle;
        if (heroImage && homepage.hero_image_url) {
            heroImage.src = homepage.hero_image_url;
            heroImage.alt = homepage.hero_title || heroImage.alt;
        }
        if (heroPrimaryBtn && homepage.hero_primary_button_text) {
            heroPrimaryBtn.textContent = homepage.hero_primary_button_text;
        }
        if (heroPrimaryBtn && homepage.hero_primary_button_href) {
            heroPrimaryBtn.href = homepage.hero_primary_button_href;
        }
        if (heroSecondaryBtn && homepage.hero_secondary_button_text) {
            heroSecondaryBtn.textContent = homepage.hero_secondary_button_text;
        }
        if (heroSecondaryBtn && homepage.hero_secondary_button_href) {
            heroSecondaryBtn.href = homepage.hero_secondary_button_href;
        }
        if (contactTitle && homepage.contact_section_title) {
            contactTitle.textContent = homepage.contact_section_title;
        }
        if (contactSubtitle && homepage.contact_section_subtitle) {
            contactSubtitle.textContent = homepage.contact_section_subtitle;
        }
        if (contactAddress && homepage.contact_address) {
            contactAddress.textContent = homepage.contact_address;
        }
        if (contactPhone && homepage.contact_phone) {
            contactPhone.textContent = homepage.contact_phone;
        }
        if (contactEmail && homepage.contact_email) {
            contactEmail.textContent = homepage.contact_email;
        }
        if (merchantNoticeTitle && homepage.merchant_notice_title) {
            merchantNoticeTitle.textContent = homepage.merchant_notice_title;
        }
        if (merchantNoticeText && homepage.merchant_notice_text) {
            merchantNoticeText.textContent = homepage.merchant_notice_text;
        }
        if (merchantQuickNote && homepage.merchant_notice_text) {
            merchantQuickNote.textContent = homepage.merchant_notice_text;
        }
        if (merchantServicePublish && homepage.merchant_service_publish_text) {
            merchantServicePublish.textContent = homepage.merchant_service_publish_text;
        }
        if (merchantServiceAccount && homepage.merchant_service_account_text) {
            merchantServiceAccount.textContent = homepage.merchant_service_account_text;
        }
        if (merchantServiceNoRegister && homepage.merchant_service_no_register_text) {
            merchantServiceNoRegister.textContent = homepage.merchant_service_no_register_text;
        }
        if (merchantContactPhone && homepage.merchant_contact_phone) {
            merchantContactPhone.textContent = homepage.merchant_contact_phone;
        }
        if (merchantContactWechat && homepage.merchant_contact_wechat) {
            merchantContactWechat.textContent = homepage.merchant_contact_wechat;
        }
        if (merchantContactEmail && homepage.merchant_contact_email) {
            merchantContactEmail.textContent = homepage.merchant_contact_email;
        }
        if (homepage.site_name) {
            document.title = homepage.site_name;
        }
    } catch (error) {
        console.error('Load homepage config failed:', error);
    }
}

// 初始化所有功能
function init() {
    loadHomepageConfig();
    smoothScroll();
    navbarScrollEffect();
    featureCardEffects();
    pricingCardEffects();
    validateForms();
    handleSubscribeForm();
    loadingAnimation();
}

// 页面加载完成后初始化
window.addEventListener('DOMContentLoaded', init);
