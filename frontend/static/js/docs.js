if (window.SwaggerUIBundle) {
  window.SwaggerUIBundle({url: '/openapi.json', dom_id: '#swagger-ui', deepLinking: true,
    validatorUrl: null, onComplete: () => {document.querySelector('#api-fallback').hidden = true;}});
}
