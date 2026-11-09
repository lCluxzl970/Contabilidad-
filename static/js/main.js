let facturasGlobales = [];

document.addEventListener('DOMContentLoaded', () => {
    cargarResumenIVA();
    inicializarDragAndDrop();
});

/**
 * Consulta el endpoint /api/resumen-iva para refrescar las vistas y el balance
 */
async function cargarResumenIVA() {
    try {
        const response = await fetch('/api/resumen-iva');
        if (!response.ok) {
            throw new Error(`Error HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        facturasGlobales = data.facturas || [];

        const formatoMoneda = new Intl.NumberFormat('es-MX', {
            style: 'currency',
            currency: 'MXN'
        });

        // 1. Actualizar resumen fiscal derecho
        document.getElementById('txtTrasladado').textContent = formatoMoneda.format(data.iva_trasladado);
        document.getElementById('txtAcreditable').textContent = formatoMoneda.format(data.iva_acreditable);
        
        // Vista Cálculo de IVA
        const elemCalcT = document.getElementById('calcTrasladado');
        const elemCalcA = document.getElementById('calcAcreditable');
        if (elemCalcT) elemCalcT.textContent = formatoMoneda.format(data.iva_trasladado);
        if (elemCalcA) elemCalcA.textContent = formatoMoneda.format(data.iva_acreditable);

        const lblSaldo = document.getElementById('lblSaldoTitulo');
        const txtSaldo = document.getElementById('txtAPagar');

        if (data.saldo_a_favor > 0) {
            lblSaldo.textContent = 'SALDO A FAVOR';
            txtSaldo.textContent = formatoMoneda.format(data.saldo_a_favor);
            txtSaldo.style.color = '#137333';
        } else {
            lblSaldo.textContent = 'SALDO A PAGAR';
            txtSaldo.textContent = formatoMoneda.format(data.iva_a_pagar);
            txtSaldo.style.color = '#2B6CB0';
        }

        // 2. Reconstruir tablas
        renderizarTablaFacturas(facturasGlobales);
        renderizarTablaClientes(facturasGlobales);

        // 3. Renderizar las 3 gráficas del sistema
        renderizarGraficaIVA(data.iva_trasladado, data.iva_acreditable);
        renderizarGraficaBarras(data.iva_trasladado, data.iva_acreditable);
        renderizarGraficaTasas(data.desglose_tasas || {});

    } catch (error) {
        console.error('Error al conectar con la API:', error);
    }
}

/**
 * Renderiza dinámicamente las filas del Libro Contable plano
 */
function renderizarTablaFacturas(facturas) {
    const tbody = document.getElementById('tablaFacturas');
    const emptyState = document.getElementById('emptyTableState');
    const tableHeader = document.querySelector('#tablaDocumentosMain thead');
    
    tbody.innerHTML = '';

    if (!facturas || facturas.length === 0) {
        emptyState.style.display = 'block';
        tableHeader.style.display = 'none';
        document.getElementById('totalDocumentos').textContent = '0 comprobantes';
        document.getElementById('paginationInfo').textContent = 'Mostrando 0 filas';
        actualizarContadoresTabla(0, 0, 0);
        return;
    }

    emptyState.style.display = 'none';
    tableHeader.style.display = '';

    let procesados = 0;
    let pendientes = 0;
    let rechazados = 0;

    const formatoMoneda = new Intl.NumberFormat('es-MX', {
        style: 'currency',
        currency: 'MXN'
    });

    facturas.forEach(f => {
        if (f.estatus === 'Procesado') procesados++;
        else if (f.estatus === 'Pendiente') pendientes++;
        else if (f.estatus === 'Rechazado') rechazados++;

        const tipoTexto = f.tipo_comprobante === 'E' ? 'Egreso' : 'Ingreso';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${f.fecha}</td>
            <td class="text-center font-semibold">${tipoTexto}</td>
            <td class="font-mono">${f.rfc_emisor}</td>
            <td class="text-right font-mono">${formatoMoneda.format(f.subtotal)}</td>
            <td class="text-center">${f.tasa_iva}</td>
            <td class="text-right font-mono font-bold">${formatoMoneda.format(f.monto_iva)}</td>
            <td class="text-center font-semibold col-estado">${f.estatus}</td>
        `;
        tbody.appendChild(tr);
    });

    document.getElementById('totalDocumentos').textContent = `${facturas.length} comprobantes`;
    document.getElementById('paginationInfo').textContent = `Mostrando 1 - ${facturas.length} de ${facturas.length} filas`;
    actualizarContadoresTabla(procesados, pendientes, rechazados);
}

/**
 * Renderiza el directorio de clientes
 */
function renderizarTablaClientes(facturas) {
    const tbody = document.getElementById('tablaClientes');
    if (!tbody) return;
    tbody.innerHTML = '';

    const clientesMap = {};
    facturas.forEach(f => {
        if (!clientesMap[f.rfc_emisor]) {
            clientesMap[f.rfc_emisor] = {
                rfc: f.rfc_emisor,
                nombre: f.nombre_emisor || 'Razon Social No Especificada',
                conteo: 1
            };
        } else {
            clientesMap[f.rfc_emisor].conteo++;
        }
    });

    const clientesList = Object.values(clientesMap);
    if (clientesList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center">Sin clientes registrados en el periodo.</td></tr>';
        return;
    }

    clientesList.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="font-mono font-bold">${c.rfc}</td>
            <td>${c.nombre}</td>
            <td class="text-center">Moral / PM</td>
            <td class="text-right font-mono">${c.conteo} facturas</td>
        `;
        tbody.appendChild(tr);
    });
}

/**
 * Filtro de Búsqueda por Texto y Estado
 */
function filtrarTabla() {
    const searchText = document.getElementById('tableSearch').value.toLowerCase().trim();
    const estadoFilter = document.getElementById('filterEstado').value;
    const filas = document.querySelectorAll('#tablaFacturas tr');
    let visibles = 0;

    filas.forEach(fila => {
        const textoFila = fila.innerText.toLowerCase();
        const celdaEstado = fila.querySelector('.col-estado');
        const estadoTexto = celdaEstado ? celdaEstado.innerText.trim() : '';

        const coincideSearch = textoFila.includes(searchText);
        const coincideEstado = (estadoFilter === 'todos') || (estadoTexto === estadoFilter);

        if (coincideSearch && coincideEstado) {
            fila.style.display = '';
            visibles++;
        } else {
            fila.style.display = 'none';
        }
    });

    const emptyState = document.getElementById('emptyTableState');
    const tableHeader = document.querySelector('#tablaDocumentosMain thead');

    if (visibles === 0) {
        emptyState.style.display = 'block';
        tableHeader.style.display = 'none';
    } else {
        emptyState.style.display = 'none';
        tableHeader.style.display = '';
    }

    document.getElementById('paginationInfo').textContent = `Mostrando ${visibles} fila(s)`;
}

/**
 * Conmutador de Vistas (SPA - Menú Lateral)
 */
function cambiarVista(vistaId) {
    const vistas = document.querySelectorAll('.vista-modulo');
    vistas.forEach(v => v.style.display = 'none');

    const items = document.querySelectorAll('.sidebar-menu .menu-item');
    items.forEach(i => i.classList.remove('active'));

    const vistaDestino = document.getElementById(`vista-${vistaId}`);
    if (vistaDestino) {
        vistaDestino.style.display = 'block';
    }

    const menuDestino = document.getElementById(`menu-${vistaId}`);
    if (menuDestino) {
        menuDestino.classList.add('active');
    }

    const titleElem = document.getElementById('topBarTitle');
    const subElem = document.getElementById('topBarSub');

    if (vistaId === 'dashboard') {
        titleElem.textContent = 'Administración y Cálculo de IVA';
        subElem.textContent = 'Módulo de Consolidación de Impuestos Indirectos';
    } else if (vistaId === 'clientes') {
        titleElem.textContent = 'Directorio de Clientes y Proveedores';
        subElem.textContent = 'Registro de Contribuyentes Fiscales';
    } else if (vistaId === 'calculo') {
        titleElem.textContent = 'Cálculo de IVA y Liquidación Fiscal';
        subElem.textContent = 'Conciliación de Impuesto Trasladado vs Acreditable';
    } else if (vistaId === 'reportes') {
        titleElem.textContent = 'Reportes e Informes Contables';
        subElem.textContent = 'Generación de Papeles de Trabajo para la Declaración';
    } else if (vistaId === 'glosario') {
        titleElem.textContent = 'Glosario Contable y Fiscal';
        subElem.textContent = 'Definición Técnica de Términos y Conceptos del IVA';
    }
}

async function enviarFacturasAlBackend(files) {
    const statusBox = document.getElementById('uploadStatus');
    const statusText = document.getElementById('uploadStatusText');

    statusBox.style.display = 'block';
    statusText.textContent = `Procesando ${files.length} archivo(s)...`;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    try {
        const response = await fetch('/api/subir-facturas', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Error en el servidor: ${response.status}`);
        }

        const result = await response.json();
        statusText.textContent = result.mensaje;

        await cargarResumenIVA();

    } catch (error) {
        console.error('Error al subir archivos:', error);
        statusText.textContent = 'Error al procesar los comprobantes.';
    }
}

function exportarPapelTrabajo() {
    window.location.href = '/api/exportar-excel';
}

function exportarReportePDF() {
    window.location.href = '/api/exportar-pdf';
}

/**
 * 1. Gráfica de Dona Lateral
 */
function renderizarGraficaIVA(trasladado, acreditable) {
    const canvas = document.getElementById('ivaChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (window.miGraficaIVA) {
        window.miGraficaIVA.destroy();
    }

    const valTrasladado = trasladado === 0 && acreditable === 0 ? 1 : trasladado;
    const valAcreditable = trasladado === 0 && acreditable === 0 ? 0 : acreditable;

    window.miGraficaIVA = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['IVA Trasladado', 'IVA Acreditable'],
            datasets: [{
                data: [valTrasladado, valAcreditable],
                backgroundColor: ['#1F3448', '#31566B'],
                borderColor: '#FFFFFF',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 8, font: { family: 'Inter', size: 10 }, color: '#343A40' }
                }
            }
        }
    });
}

/**
 * 2. Gráfica de Barras Comparativa en Vista "Cálculo de IVA"
 */
function renderizarGraficaBarras(trasladado, acreditable) {
    const canvas = document.getElementById('chartBarrasIVA');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (window.miGraficaBarras) {
        window.miGraficaBarras.destroy();
    }

    window.miGraficaBarras = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['IVA Trasladado (Cobrado)', 'IVA Acreditable (Pagado)'],
            datasets: [{
                label: 'Monto en MXN',
                data: [trasladado, acreditable],
                backgroundColor: ['#1F3448', '#31566B'],
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { font: { family: 'Inter', size: 10 } }
                },
                x: {
                    ticks: { font: { family: 'Inter', size: 11 } }
                }
            }
        }
    });
}

/**
 * 3. Gráfica de Dona por Tasas en Vista "Reportes"
 */
function renderizarGraficaTasas(tasasMap) {
    const canvas = document.getElementById('chartTasasIVA');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (window.miGraficaTasas) {
        window.miGraficaTasas.destroy();
    }

    const labels = Object.keys(tasasMap);
    const dataValues = Object.values(tasasMap);

    window.miGraficaTasas = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataValues.every(v => v === 0) ? [1, 0, 0, 0] : dataValues,
                backgroundColor: ['#1F3448', '#31566B', '#4A5568', '#A0AEC0'],
                borderColor: '#FFFFFF',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { boxWidth: 10, font: { family: 'Inter', size: 10 } }
                }
            }
        }
    });
}

function actualizarContadoresTabla(procesados, pendientes, rechazados) {
    document.getElementById('countProcesados').textContent = procesados;
    document.getElementById('countPendientes').textContent = pendientes;
    document.getElementById('countRechazados').textContent = rechazados;
}

function inicializarDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.style.borderColor = '#31566B';
            dropZone.style.backgroundColor = '#EBF8FF';
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.style.borderColor = '#A0AEC0';
            dropZone.style.backgroundColor = '#FAFBFD';
        });
    });

    dropZone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            enviarFacturasAlBackend(files);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            enviarFacturasAlBackend(fileInput.files);
        }
    });
}