import React, { useState, useEffect, useCallback } from 'react';
import { getDrivers, getProviders, updateDriver, createProviderInline, getVehicleTypes } from '../../lib/api';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '../ui/dialog';
import { Search, Pencil, Loader2, Truck, Plus, ChevronLeft, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';

export const SettingsDriversTab = () => {
    const [drivers, setDrivers] = useState([]);
    const [providers, setProviders] = useState([]);
    const [vehicleTypes, setVehicleTypes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pages, setPages] = useState(1);
    const [search, setSearch] = useState('');
    const [filterProvider, setFilterProvider] = useState('all');
    const [filterStatus, setFilterStatus] = useState('all');

    // Edit modal
    const [showEditModal, setShowEditModal] = useState(false);
    const [editingDriver, setEditingDriver] = useState(null);
    const [editForm, setEditForm] = useState({ provider_id: '', vehicle_type: '', vehicle_custom: '', status: 'active' });
    const [saving, setSaving] = useState(false);

    // Inline provider creation
    const [showNewProviderModal, setShowNewProviderModal] = useState(false);
    const [newProviderForm, setNewProviderForm] = useState({ name: '', contact_name: '', contact_phone: '', rfc: '' });
    const [creatingProvider, setCreatingProvider] = useState(false);

    const fetchDrivers = useCallback(async () => {
        setLoading(true);
        try {
            const params = { page, limit: 25 };
            if (search) params.search = search;
            if (filterProvider && filterProvider !== 'all') params.provider_id = filterProvider;
            if (filterStatus && filterStatus !== 'all') params.status = filterStatus;
            const res = await getDrivers(params);
            setDrivers(res.data.data);
            setTotal(res.data.total);
            setPages(res.data.pages);
        } catch {
            toast.error('Error al cargar drivers');
        } finally {
            setLoading(false);
        }
    }, [page, search, filterProvider, filterStatus]);

    useEffect(() => { fetchDrivers(); }, [fetchDrivers]);

    useEffect(() => {
        Promise.allSettled([getProviders(), getVehicleTypes()]).then(([provRes, vtRes]) => {
            if (provRes.status === 'fulfilled') setProviders(provRes.value.data);
            if (vtRes.status === 'fulfilled') setVehicleTypes(vtRes.value.data);
        });
    }, []);

    const handleSearch = (val) => { setSearch(val); setPage(1); };
    const handleFilterProvider = (val) => { setFilterProvider(val); setPage(1); };
    const handleFilterStatus = (val) => { setFilterStatus(val); setPage(1); };

    const openEditModal = (driver) => {
        setEditingDriver(driver);
        setEditForm({
            provider_id: driver.provider_id || '',
            vehicle_type: driver.vehicle_type || '',
            vehicle_custom: driver.vehicle_custom || '',
            status: driver.status || 'active',
        });
        setShowEditModal(true);
    };

    const handleSaveDriver = async () => {
        if (!editForm.provider_id) { toast.error('El proveedor es requerido'); return; }
        setSaving(true);
        try {
            await updateDriver(editingDriver.id, editForm);
            toast.success('Driver actualizado');
            setShowEditModal(false);
            fetchDrivers();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al guardar');
        } finally {
            setSaving(false);
        }
    };

    const handleCreateProviderInline = async () => {
        if (!newProviderForm.name.trim()) { toast.error('Nombre requerido'); return; }
        setCreatingProvider(true);
        try {
            const res = await createProviderInline({ ...newProviderForm, created_via: 'settings' });
            const newProv = res.data;
            if (!newProv.already_existed) {
                toast.success(`Proveedor "${newProv.name}" creado`);
                const provRes = await getProviders();
                setProviders(provRes.data);
            } else {
                toast.info(`Proveedor "${newProv.name}" ya existe`);
            }
            setEditForm(prev => ({ ...prev, provider_id: newProv.id }));
            setShowNewProviderModal(false);
            setNewProviderForm({ name: '', contact_name: '', contact_phone: '', rfc: '' });
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al crear proveedor');
        } finally {
            setCreatingProvider(false);
        }
    };

    const getStatusBadge = (status) => {
        if (status === 'active') return <span className="px-2 py-0.5 text-xs font-medium rounded bg-emerald-100 text-emerald-700">Activo</span>;
        return <span className="px-2 py-0.5 text-xs font-medium rounded bg-slate-200 text-slate-600">Inactivo</span>;
    };

    return (
        <div className="space-y-4">
            {/* Filters */}
            <div className="flex items-center gap-3 flex-wrap">
                <div className="relative flex-1 max-w-sm">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input value={search} onChange={(e) => handleSearch(e.target.value)} placeholder="Buscar driver..." className="pl-9" data-testid="search-drivers-input" />
                </div>
                <Select value={filterProvider} onValueChange={handleFilterProvider}>
                    <SelectTrigger className="w-[180px]" data-testid="filter-driver-provider">
                        <SelectValue placeholder="Proveedor" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todos los proveedores</SelectItem>
                        {providers.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                    </SelectContent>
                </Select>
                <Select value={filterStatus} onValueChange={handleFilterStatus}>
                    <SelectTrigger className="w-[140px]" data-testid="filter-driver-status">
                        <SelectValue placeholder="Estado" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todos</SelectItem>
                        <SelectItem value="active">Activo</SelectItem>
                        <SelectItem value="inactive">Inactivo</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {/* Table */}
            <Card>
                <CardContent className="p-0">
                    {loading ? (
                        <div className="p-8 flex justify-center"><Loader2 className="w-8 h-8 animate-spin text-slate-400" /></div>
                    ) : drivers.length === 0 ? (
                        <div className="text-center py-12">
                            <Truck className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                            <p className="text-slate-500">{search ? 'Sin resultados' : 'No hay drivers registrados'}</p>
                        </div>
                    ) : (
                        <table className="data-table w-full">
                            <thead>
                                <tr>
                                    <th>Driver Name</th>
                                    <th>Proveedor (Team)</th>
                                    <th>Vehiculo</th>
                                    <th>Estado</th>
                                    <th>Rutas</th>
                                    <th>Acciones</th>
                                </tr>
                            </thead>
                            <tbody>
                                {drivers.map((d) => (
                                    <tr key={d.id} data-testid={`driver-row-${d.id}`}>
                                        <td className="font-medium">{d.name}</td>
                                        <td className="text-slate-600">{d.provider_name || <span className="text-slate-400">Sin asignar</span>}</td>
                                        <td className="text-slate-600 capitalize">{d.vehicle_type || <span className="text-slate-400">-</span>}</td>
                                        <td>{getStatusBadge(d.status)}</td>
                                        <td className="font-mono text-sm">{d.total_routes || 0}</td>
                                        <td>
                                            <Button variant="ghost" size="icon" onClick={() => openEditModal(d)} data-testid={`edit-driver-${d.id}`}>
                                                <Pencil className="w-4 h-4" />
                                            </Button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </CardContent>
            </Card>

            {/* Pagination */}
            {pages > 1 && (
                <div className="flex items-center justify-between text-sm text-slate-500">
                    <span>{total} drivers - Pagina {page} de {pages}</span>
                    <div className="flex gap-1">
                        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)} data-testid="drivers-prev-page"><ChevronLeft className="w-4 h-4" /></Button>
                        <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(p => p + 1)} data-testid="drivers-next-page"><ChevronRight className="w-4 h-4" /></Button>
                    </div>
                </div>
            )}

            {/* Edit Driver Modal */}
            <Dialog open={showEditModal} onOpenChange={setShowEditModal}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Editar Driver</DialogTitle>
                        <DialogDescription>Modifica los datos del driver. Los cambios aplican solo a futuras cargas.</DialogDescription>
                    </DialogHeader>
                    {editingDriver && (
                        <div className="space-y-4">
                            {/* Read-only fields */}
                            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-sm">
                                <div><p className="text-xs text-slate-500">Driver Name</p><p className="text-sm font-medium">{editingDriver.name}</p></div>
                                <div><p className="text-xs text-slate-500">ID interno</p><p className="text-xs font-mono text-slate-600">{editingDriver.id?.slice(0, 12)}...</p></div>
                                <div><p className="text-xs text-slate-500">Primera carga</p><p className="text-sm">{editingDriver.first_upload_at?.slice(0, 10) || '-'}</p></div>
                                <div><p className="text-xs text-slate-500">Total rutas</p><p className="text-sm font-mono">{editingDriver.total_routes || 0}</p></div>
                            </div>

                            {/* Editable: Provider */}
                            <div className="space-y-2">
                                <Label>Proveedor (Team) *</Label>
                                <div className="flex gap-2">
                                    <Select value={editForm.provider_id} onValueChange={(v) => setEditForm(prev => ({ ...prev, provider_id: v }))}>
                                        <SelectTrigger data-testid="edit-driver-provider-select" className="flex-1">
                                            <SelectValue placeholder="Seleccionar proveedor" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {providers.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                    <Button variant="outline" size="icon" onClick={() => setShowNewProviderModal(true)} title="Crear proveedor nuevo" data-testid="create-provider-inline-btn">
                                        <Plus className="w-4 h-4" />
                                    </Button>
                                </div>
                            </div>

                            {/* Editable: Vehicle */}
                            <div className="space-y-2">
                                <Label>Vehiculo</Label>
                                <Select value={editForm.vehicle_type} onValueChange={(v) => setEditForm(prev => ({ ...prev, vehicle_type: v, vehicle_custom: v === 'otro' ? prev.vehicle_custom : '' }))}>
                                    <SelectTrigger data-testid="edit-driver-vehicle-select">
                                        <SelectValue placeholder="Seleccionar vehiculo" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {vehicleTypes.map(vt => <SelectItem key={vt} value={vt} className="capitalize">{vt}</SelectItem>)}
                                        <SelectItem value="otro">Otro</SelectItem>
                                    </SelectContent>
                                </Select>
                                {editForm.vehicle_type === 'otro' && (
                                    <Input value={editForm.vehicle_custom} onChange={(e) => setEditForm(prev => ({ ...prev, vehicle_custom: e.target.value }))} placeholder="Especificar vehiculo..." data-testid="edit-driver-vehicle-custom" />
                                )}
                            </div>

                            {/* Editable: Status */}
                            <div className="space-y-2">
                                <Label>Estado</Label>
                                <Select value={editForm.status} onValueChange={(v) => setEditForm(prev => ({ ...prev, status: v }))}>
                                    <SelectTrigger data-testid="edit-driver-status-select">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="active">Activo</SelectItem>
                                        <SelectItem value="inactive">Inactivo</SelectItem>
                                    </SelectContent>
                                </Select>
                                {editForm.status === 'inactive' && (
                                    <p className="text-xs text-amber-600 bg-amber-50 p-2 rounded">Este driver no sera asignable en nuevas cargas hasta que se reactive.</p>
                                )}
                            </div>
                        </div>
                    )}
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowEditModal(false)}>Cancelar</Button>
                        <Button onClick={handleSaveDriver} disabled={saving} data-testid="save-driver-btn">
                            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Guardar cambios
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* New Provider Inline Modal */}
            <Dialog open={showNewProviderModal} onOpenChange={setShowNewProviderModal}>
                <DialogContent className="max-w-sm">
                    <DialogHeader><DialogTitle className="font-heading">Crear proveedor nuevo</DialogTitle></DialogHeader>
                    <div className="space-y-3">
                        <div className="space-y-1"><Label>Nombre *</Label><Input value={newProviderForm.name} onChange={(e) => setNewProviderForm(p => ({ ...p, name: e.target.value }))} placeholder="Nombre del proveedor" data-testid="inline-provider-name" /></div>
                        <div className="space-y-1"><Label>RFC / Razon social</Label><Input value={newProviderForm.rfc} onChange={(e) => setNewProviderForm(p => ({ ...p, rfc: e.target.value }))} placeholder="Opcional" /></div>
                        <div className="space-y-1"><Label>Contacto</Label><Input value={newProviderForm.contact_name} onChange={(e) => setNewProviderForm(p => ({ ...p, contact_name: e.target.value }))} placeholder="Opcional" /></div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowNewProviderModal(false)}>Cancelar</Button>
                        <Button onClick={handleCreateProviderInline} disabled={creatingProvider} data-testid="create-inline-provider-btn">
                            {creatingProvider && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Crear proveedor
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
};
