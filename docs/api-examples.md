# Exemplos da API

## Saúde do backend

```bash
curl http://localhost:8080/api/v1/health
```

## Categorias

```bash
curl http://localhost:8080/api/v1/categories
```

## Saúde dos workers (REST e gRPC)

```bash
curl http://localhost:8080/api/v1/workers/health
```

## Classificação distribuída via REST

```bash
curl -X POST "http://localhost:8080/api/v1/classifications?strategy=distributed&protocol=rest" \
  -F "files=@imagem1.jpg" \
  -F "files=@imagem2.jpg"
```

## Classificação distribuída via gRPC (RPC de alto desempenho)

```bash
curl -X POST "http://localhost:8080/api/v1/classifications?strategy=distributed&protocol=grpc" \
  -F "files=@imagem1.jpg" \
  -F "files=@imagem2.jpg"
```

## Classificação em um único worker

```bash
curl -X POST "http://localhost:8080/api/v1/classifications?strategy=single-worker&protocol=grpc" \
  -F "files=@imagem1.jpg" \
  -F "files=@imagem2.jpg"
```

## Comparação Sequencial vs Distribuído (Speedup)

```bash
curl -X POST "http://localhost:8080/api/v1/experiments/compare?protocol=grpc" \
  -F "files=@imagem1.jpg" \
  -F "files=@imagem2.jpg" \
  -F "files=@imagem3.jpg" \
  -F "files=@imagem4.jpg"
```

## Comparação de Transporte: REST vs gRPC

Compara a latência de serialização e transmissão entre REST e gRPC com o mesmo lote de imagens:

```bash
curl -X POST "http://localhost:8080/api/v1/experiments/compare-protocols" \
  -F "files=@imagem1.jpg" \
  -F "files=@imagem2.jpg" \
  -F "files=@imagem3.jpg" \
  -F "files=@imagem4.jpg"
```
