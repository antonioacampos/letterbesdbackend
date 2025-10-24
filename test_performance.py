#!/usr/bin/env python3
"""
Script de teste de performance para o backend do Letterboxd
"""

import requests
import time
import json

def test_endpoint(url, description):
    """Testa um endpoint e mede o tempo de resposta"""
    print(f"\n🧪 Testando: {description}")
    print(f"URL: {url}")
    
    start_time = time.time()
    try:
        response = requests.get(url, timeout=15)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        print(f"✅ Status: {response.status_code}")
        print(f"⏱️  Tempo: {response_time:.2f}s")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if 'recomendacoes' in data:
                    print(f"📊 Recomendações: {len(data['recomendacoes'])}")
                if 'processing_time' in data.get('metadata', {}):
                    print(f"⚡ Processing time: {data['metadata']['processing_time']:.2f}s")
                if 'mode' in data.get('metadata', {}):
                    print(f"🔧 Mode: {data['metadata']['mode']}")
            except:
                print("📄 Response não é JSON")
        else:
            print(f"❌ Erro: {response.text[:100]}")
            
    except requests.exceptions.Timeout:
        print("⏰ TIMEOUT - Requisição demorou mais de 15s")
    except Exception as e:
        print(f"❌ Erro: {str(e)}")
    
    return response_time if 'response_time' in locals() else 15.0

def main():
    base_url = input("Digite a URL base da API (ex: https://seu-app.railway.app): ").strip()
    if not base_url:
        base_url = "http://localhost:5000"
    
    print(f"🚀 Testando performance da API em: {base_url}")
    
    # Teste 1: Health check
    test_endpoint(f"{base_url}/health", "Health Check")
    
    # Teste 2: Memory status
    test_endpoint(f"{base_url}/api/memory", "Memory Status")
    
    # Teste 3: Test user (quick)
    test_endpoint(f"{base_url}/api/test/gutomp4", "Test User (gutomp4)")
    
    # Teste 4: Cache user
    print(f"\n🧪 Testando: Cache User (gutomp4)")
    print(f"URL: {base_url}/api/cache/gutomp4")
    start_time = time.time()
    try:
        response = requests.get(f"{base_url}/api/cache/gutomp4", timeout=15)
        end_time = time.time()
        response_time = end_time - start_time
        print(f"✅ Status: {response.status_code}")
        print(f"⏱️  Tempo: {response_time:.2f}s")
        if response.status_code == 200:
            data = response.json()
            print(f"📊 Cached users: {data.get('cached_users', [])}")
    except Exception as e:
        print(f"❌ Erro: {str(e)}")
    
    # Teste 5: Recommendations (should be fast now)
    test_endpoint(f"{base_url}/api/recomendacoes/gutomp4", "Recommendations (gutomp4)")
    
    # Teste 6: Another user (should return fallback)
    test_endpoint(f"{base_url}/api/recomendacoes/filmaria", "Recommendations (filmaria - fallback)")
    
    print(f"\n✅ Testes concluídos!")
    print(f"\n💡 Dicas:")
    print(f"   - Se recommendations demorarem > 5s, há problema")
    print(f"   - Se retornar fallback, usuário não está em cache")
    print(f"   - Use /api/cache/<usuario> para cachear usuários")
    print(f"   - Use /api/memory para monitorar uso de memória")

if __name__ == "__main__":
    main()
