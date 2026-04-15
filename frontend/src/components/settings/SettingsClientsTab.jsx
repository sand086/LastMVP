import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Input } from '../ui/input';
import { Plus, Pencil, Trash2, Loader2, Building2, Search } from 'lucide-react';

export const SettingsClientsTab = ({
    loading,
    searchClients,
    setSearchClients,
    sortedClients,
    filteredClients,
    ClientSortHeader,
    handleOpenEntityModal,
    handleDeleteEntity,
}) => (
    <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
            <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <Input
                    value={searchClients}
                    onChange={(e) => setSearchClients(e.target.value)}
                    placeholder="Buscar cliente..."
                    className="pl-9"
                    data-testid="search-clients-input"
                />
            </div>
            <Button onClick={() => handleOpenEntityModal('client')} data-testid="add-client-btn">
                <Plus className="w-4 h-4 mr-2" />
                Nuevo cliente
            </Button>
        </div>

        <Card>
            <CardContent className="p-0">
                {loading ? (
                    <div className="p-8 flex justify-center">
                        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                    </div>
                ) : filteredClients.length === 0 ? (
                    <div className="text-center py-12">
                        <Building2 className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                        <p className="text-slate-500">{searchClients ? 'Sin resultados' : 'No hay clientes registrados'}</p>
                    </div>
                ) : (
                    <table className="data-table w-full">
                        <thead>
                            <tr>
                                <ClientSortHeader field="name">Nombre</ClientSortHeader>
                                <th>ID</th>
                                <th>Acciones</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sortedClients.map((client) => (
                                <tr key={client.id} data-testid={`client-row-${client.id}`}>
                                    <td className="font-medium">{client.name}</td>
                                    <td className="font-mono text-xs text-slate-500">{client.id}</td>
                                    <td>
                                        <div className="flex items-center gap-1">
                                            <Button variant="ghost" size="icon" onClick={() => handleOpenEntityModal('client', client)} data-testid={`edit-client-${client.id}`}>
                                                <Pencil className="w-4 h-4" />
                                            </Button>
                                            <Button variant="ghost" size="icon" className="text-red-600" onClick={() => handleDeleteEntity('client', client.id)} data-testid={`delete-client-${client.id}`}>
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
