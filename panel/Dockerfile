FROM php:8.1-apache

# PHP uzantılarını quraşdırırıq (MySQL üçün)
RUN docker-php-ext-install pdo pdo_mysql mysqli

# Faylları serverə kopyalayırıq
COPY . /var/www/html/

# Apache-ni işə salırıq
RUN a2enmod rewrite
EXPOSE 80
