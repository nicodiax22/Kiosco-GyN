# Plan de mejoras - Kiosco Digital v2.0
# Estado: EN PROGRESO - actualizar al completar cada item

## COMPLETADO
- [x] Sistema base (dashboard, POS, stock, historial, reportes, caja, config)
- [x] Fix caja: reabrir después de cerrar
- [x] Ícono y acceso directo en escritorio
- [x] Push a GitHub nicodiax22/Kiosco-GyN

## PENDIENTE (en orden de prioridad)

### ALTA PRIORIDAD
- [ ] 1. Editar cantidad directamente en el carrito (inline input en cada fila)
- [ ] 2. Ticket imprimible (window.print con formato 80mm térmica)
- [ ] 3. Notificación automática de stock bajo al abrir el sistema
- [ ] 4. Historial de movimientos de stock (conectar tabla movimientos_stock real)
- [ ] 5. Backup de base de datos (endpoint /api/backup que descarga el .db)

### MEDIA PRIORIDAD
- [ ] 6. Buscador en POS con teclas 1/2/3 para seleccionar de lista
- [ ] 7. Modo pantalla completa (F11 toggle)
- [ ] 8. Estadísticas de rentabilidad por categoría en Reportes
- [ ] 9. Filtro por fechas en Stock (productos sin movimiento)
- [ ] 10. Importador CSV masivo de precios

### BAJA PRIORIDAD
- [ ] 11. Modo oscuro
- [ ] 12. Multi-usuario con PIN
- [ ] 13. Cuenta corriente / fiados
- [ ] 14. Cierre de caja con desglose de billetes
- [ ] 15. Pagos mixtos en una sola venta

## ARCHIVO A MODIFICAR
C:\Users\Nico\Desktop\KIOSCO GABI\kiosco.py

## COMO RETOMAR
Leer este archivo, ver qué items están sin [ ] y seguir desde el primero pendiente.
Al terminar cada uno: marcar [x], hacer git add + commit + push.
