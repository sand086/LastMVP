import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Input } from '../ui/input';
import { Plus, Pencil, Trash2, Loader2, Truck, Search } from 'lucide-react';

export const SettingsProvidersTab = ({
    loading,
    searchProviders,
    setSearchProviders,
    sortedProviders,
    filteredProviders,
    ProvSortHeader,
    handleOpenEntityModal,
    handleDeleteEntity,
}) => (
    <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
            <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <Input
                    value={searchProviders}
                    onChange={(e) => setSearchProviders(e.target.value)}
                    placeholder="Buscar proveedor..."
                    className="pl-9"
                    data-testid="search-providers-input"
                />
            </div>
            <Button onClick={() => handleOpenEntityModal('provider')} data-testid="add-provider-btn">
                <Plus className="w-4 h-4 mr-2" />
                Nuevo proveedor
            </Button>
        </div>

        <Card>
            <CardContent className="p-0">
                {loading ? (
                    <div className="p-8 flex justify-center">
                        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                    </div>
                ) : filteredProviders.length === 0 ? (
                    <div className="text-center py-12">
                        <Truck className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                        <p className="text-slate-500">{searchProviders ? 'Sin resultados' : 'No hay proveedores registrados'}</p>
                    </div>
                ) : (
                    <table className="data-table w-full">
                        <thead>
                            <tr>
                                <ProvSortHeader field="name">Nombre</ProvSortHeader>
                                <ProvSortHeader field="contact_name">Contacto</ProvSortHeader>
                                <ProvSortHeader field="contact_phone">Telefono</ProvSortHeader>
                                <th>Acciones</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sortedProviders.map((provider) => (
                                <tr key={provider.id} data-testid={`provider-row-${provider.id}`}>
                                    <td className="font-medium">{provider.name}</td>
                                    <td className="text-slate-600">{provider.contact_name || '-'}</td>
                                    <td className="font-mono text-sm">{provider.contact_phone || '-'}</td>
                                    <td>
                                        <div className="flex items-center gap-1">
                                            <Button variant="ghost" size="icon" onClick={() => handleOpenEntityModal('provider', provider)} data-testid={`edit-provider-${provider.id}`}>
                                                <Pencil className="w-4 h-4" />
                                            </Button>
                                            <Button variant="ghost" size="icon" className="text-red-600" onClick={() => handleDeleteEntity('provider', provider.id)} data-testid={`delete-provider-${provider.id}`}>
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </CardContent>
        </Card>
    </div>
);
